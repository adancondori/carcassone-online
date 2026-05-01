"""Service functions for Carcassonne Scoreboard.

Core operations: add_score, undo_last, rollback_to, recalculate_score.
Game lifecycle: create_game, add_player, remove_player, start_game.
Query helpers: get_game_state.

All functions take a Session as first argument for explicit transaction control.
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Game, Player, ScoreAction, ScoreEntry


# Color hex map for template lookups (avoids circular import with web.dependencies).
COLOR_HEX_MAP = {
    "blue": "#0055BF", "red": "#CC0000", "green": "#237F23",
    "yellow": "#F2CD00", "black": "#1A1A1A", "pink": "#FF69B4",
}


@dataclass
class GameState:
    """Snapshot of a game's current state for template rendering."""
    game: Game
    players: list[Player]
    action_count: int


def get_game_state(session: Session, game_id: int) -> GameState:
    """Load game, ranked players, and active action count.

    Args:
        session: Database session.
        game_id: The game to load.

    Returns:
        GameState with game, players sorted by score_total DESC, action count.

    Raises:
        ValueError: If game_id does not exist.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")

    players = session.exec(
        select(Player)
        .where(Player.game_id == game_id)
        .order_by(Player.score_total.desc(), Player.turn_order)
    ).all()

    action_count = session.exec(
        select(func.count(ScoreAction.id))
        .where(ScoreAction.game_id == game_id)
        .where(ScoreAction.is_undone == False)  # noqa: E712
    ).one()

    return GameState(game=game, players=list(players), action_count=action_count)


def add_score(
    session: Session,
    game_id: int,
    player_points: list[tuple[int, int]],
    event_type: str,
    description: str | None = None,
) -> ScoreAction:
    """Create a ScoreAction with ScoreEntries and update player score totals.

    Args:
        session: Database session.
        game_id: The game to score in.
        player_points: List of (player_id, points) tuples.
        event_type: Scoring event type (e.g. 'ROAD_COMPLETED').
        description: Optional description of the scoring event.

    Returns:
        The created ScoreAction.

    Raises:
        ValueError: If a player_id does not exist.
    """
    action = ScoreAction(
        game_id=game_id,
        event_type=event_type,
        description=description,
    )
    session.add(action)
    session.flush()  # Get action.id without committing

    for player_id, points in player_points:
        player = session.get(Player, player_id)
        if player is None:
            raise ValueError(f"Player {player_id} not found")

        score_before = player.score_total
        player.score_total += points

        entry = ScoreEntry(
            action_id=action.id,
            player_id=player_id,
            points=points,
            score_before=score_before,
            score_after=player.score_total,
        )
        session.add(entry)

    session.commit()
    return action


def undo_last(session: Session, game_id: int) -> ScoreAction | None:
    """Mark the last active ScoreAction as undone and recalculate affected scores.

    Args:
        session: Database session.
        game_id: The game to undo in.

    Returns:
        The undone ScoreAction, or None if no active actions exist.
    """
    statement = (
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .where(ScoreAction.is_undone == False)  # noqa: E712
        .order_by(ScoreAction.id.desc())
        .limit(1)
    )
    last_action = session.exec(statement).first()
    if last_action is None:
        return None

    last_action.is_undone = True

    # Recalculate all affected players from entries
    entries = session.exec(
        select(ScoreEntry).where(ScoreEntry.action_id == last_action.id)
    ).all()
    affected_player_ids = {e.player_id for e in entries}
    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return last_action


def rollback_to(session: Session, game_id: int, action_id: int) -> int:
    """Mark all active actions after action_id as undone and recalculate scores.

    Args:
        session: Database session.
        game_id: The game to rollback in.
        action_id: The action to rollback to (this action stays active).

    Returns:
        Number of actions that were undone.
    """
    statement = (
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .where(ScoreAction.id > action_id)
        .where(ScoreAction.is_undone == False)  # noqa: E712
    )
    actions = session.exec(statement).all()
    if not actions:
        return 0

    affected_player_ids: set[int] = set()
    for action in actions:
        action.is_undone = True
        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action.id)
        ).all()
        for entry in entries:
            affected_player_ids.add(entry.player_id)

    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return len(actions)


def recalculate_score(session: Session, player_id: int) -> int:
    """Recalculate a player's score from active entries and update score_total.

    This is the source of truth for player scores. It queries the SUM of
    all ScoreEntry.points where the parent ScoreAction is not undone.

    Args:
        session: Database session.
        player_id: The player whose score to recalculate.

    Returns:
        The recalculated score total.
    """
    total = session.exec(
        select(func.coalesce(func.sum(ScoreEntry.points), 0))
        .join(ScoreAction, ScoreEntry.action_id == ScoreAction.id)
        .where(ScoreEntry.player_id == player_id)
        .where(ScoreAction.is_undone == False)  # noqa: E712
    ).one()

    player = session.get(Player, player_id)
    player.score_total = total
    session.flush()
    return total


# ── Game lifecycle ──────────────────────────────────────────


def create_game(session: Session, name: str) -> Game:
    """Create a new game in 'setup' status.

    Args:
        session: Database session.
        name: Display name for the game.

    Returns:
        The created Game.
    """
    game = Game(name=name, status="setup")
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


def add_player(
    session: Session, game_id: int, name: str, color: str
) -> Player:
    """Add a player to a game that is in setup status.

    Args:
        session: Database session.
        game_id: The game to add the player to.
        name: Player display name.
        color: Player color key (e.g. 'blue', 'red').

    Returns:
        The created Player.

    Raises:
        ValueError: If game is not in setup, or already has 6 players.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "setup":
        raise ValueError("Can only add players during setup")

    existing = session.exec(
        select(func.count(Player.id)).where(Player.game_id == game_id)
    ).one()
    if existing >= 6:
        raise ValueError("Maximum 6 players per game")

    turn_order = existing + 1
    player = Player(
        game_id=game_id, name=name, color=color, turn_order=turn_order
    )
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


def remove_player(session: Session, game_id: int, player_id: int) -> None:
    """Remove a player from a game in setup status and reorder remaining.

    Args:
        session: Database session.
        game_id: The game the player belongs to.
        player_id: The player to remove.

    Raises:
        ValueError: If game is not in setup or player not found.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "setup":
        raise ValueError("Can only remove players during setup")

    player = session.get(Player, player_id)
    if player is None or player.game_id != game_id:
        raise ValueError(f"Player {player_id} not found in game {game_id}")

    session.delete(player)
    session.flush()

    # Reorder remaining players sequentially
    remaining = session.exec(
        select(Player)
        .where(Player.game_id == game_id)
        .order_by(Player.turn_order)
    ).all()
    for i, p in enumerate(remaining, start=1):
        p.turn_order = i

    session.commit()


def start_game(session: Session, game_id: int) -> Game:
    """Transition a game from setup to playing status.

    Args:
        session: Database session.
        game_id: The game to start.

    Returns:
        The updated Game.

    Raises:
        ValueError: If game is not in setup or has fewer than 2 players.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "setup":
        raise ValueError("Can only start a game in setup status")

    player_count = session.exec(
        select(func.count(Player.id)).where(Player.game_id == game_id)
    ).one()
    if player_count < 2:
        raise ValueError("Need at least 2 players to start")

    game.status = "playing"
    session.commit()
    session.refresh(game)
    return game
