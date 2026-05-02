"""Service functions for Carcassonne Scoreboard.

Core operations: add_score, undo_last, rollback_to, recalculate_score.
Game lifecycle: create_game, add_player, remove_player, start_game,
               begin_scoring, finish_game.
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

# Event types valid during the playing (mid-game) phase.
PLAYING_EVENT_TYPES = frozenset({
    "ROAD_COMPLETED", "CITY_COMPLETED", "MONASTERY_COMPLETED", "MANUAL",
})

# Event types valid during the scoring (end-game) phase.
SCORING_EVENT_TYPES = frozenset({
    "ROAD_FINAL", "CITY_FINAL", "MONASTERY_FINAL", "FARM_FINAL", "MANUAL",
})


@dataclass
class ActionDetail:
    """A scoring action with resolved player names/colors for template rendering."""
    action: ScoreAction
    entries: list[dict]  # Each dict: {"player_name": str, "player_color": str, "points": int}


@dataclass
class GameState:
    """Snapshot of a game's current state for template rendering."""
    game: Game
    players: list[Player]
    action_count: int
    action_details: list[ActionDetail] = None

    def __post_init__(self):
        if self.action_details is None:
            self.action_details = []


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

    # Load all actions (active and undone) with their entries for history panel
    actions = session.exec(
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .order_by(ScoreAction.id)
    ).all()

    # Build player lookup for entry rendering
    player_map = {p.id: p for p in players}

    action_details = []
    for action in actions:
        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action.id)
        ).all()
        entry_dicts = [
            {
                "player_name": player_map[e.player_id].name if e.player_id in player_map else "?",
                "player_color": player_map[e.player_id].color if e.player_id in player_map else "black",
                "points": e.points,
            }
            for e in entries
        ]
        action_details.append(ActionDetail(action=action, entries=entry_dicts))

    return GameState(
        game=game,
        players=list(players),
        action_count=action_count,
        action_details=action_details,
    )


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
        ValueError: If game state doesn't allow this event type, or player_id not found.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")

    if game.status == "playing":
        if event_type not in PLAYING_EVENT_TYPES:
            raise ValueError(
                f"Event type '{event_type}' is not valid during playing state"
            )
    elif game.status == "scoring":
        if event_type not in SCORING_EVENT_TYPES:
            raise ValueError(
                f"Event type '{event_type}' is not valid during scoring state"
            )
    else:
        raise ValueError(f"Cannot add scores in '{game.status}' state")

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

    Raises:
        ValueError: If game is in finished state.
    """
    game = session.get(Game, game_id)
    if game is not None and game.status == "finished":
        raise ValueError("Cannot undo in a finished game")

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

    Raises:
        ValueError: If game is in finished state.
    """
    game = session.get(Game, game_id)
    if game is not None and game.status == "finished":
        raise ValueError("Cannot rollback in a finished game")

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


def begin_scoring(session: Session, game_id: int) -> Game:
    """Transition a game from playing to scoring status.

    Args:
        session: Database session.
        game_id: The game to transition.

    Returns:
        The updated Game.

    Raises:
        ValueError: If game is not in playing status.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "playing":
        raise ValueError("Can only begin scoring for a game in playing status")

    game.status = "scoring"
    session.commit()
    session.refresh(game)
    return game


def finish_game(session: Session, game_id: int) -> Game:
    """Transition a game from scoring to finished status.

    Args:
        session: Database session.
        game_id: The game to finish.

    Returns:
        The updated Game.

    Raises:
        ValueError: If game is not in scoring status.
    """
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "scoring":
        raise ValueError("Can only finish a game in scoring status")

    game.status = "finished"
    session.commit()
    session.refresh(game)
    return game


# ── Dashboard stats ────────────────────────────────────────


@dataclass
class DashboardStats:
    """Aggregate statistics for the home dashboard."""
    total_games: int
    finished_games: int
    active_games: int
    total_actions: int
    top_winners: list[dict]       # [{"name": str, "wins": int, "color": str}]
    recent_games: list[dict]      # [{"id", "name", "status", "created_at", "players", "winner"}]
    games_by_week: list[dict]     # [{"week": str, "count": int}]


def get_dashboard_stats(session: Session) -> DashboardStats:
    """Compute aggregate stats across all games for the home dashboard."""
    # Total / finished / active counts
    total_games = session.exec(select(func.count(Game.id))).one()
    finished_games = session.exec(
        select(func.count(Game.id)).where(Game.status == "finished")
    ).one()
    active_games = session.exec(
        select(func.count(Game.id)).where(Game.status.in_(["playing", "scoring"]))
    ).one()

    # Total scoring actions (across all games, only active ones)
    total_actions = session.exec(
        select(func.count(ScoreAction.id))
        .where(ScoreAction.is_undone == False)  # noqa: E712
    ).one()

    # Top winners: players who won finished games (highest score in each finished game)
    finished = session.exec(
        select(Game).where(Game.status == "finished")
    ).all()

    winner_counts: dict[str, dict] = {}  # name -> {"wins": int, "color": str}
    for game in finished:
        players = session.exec(
            select(Player)
            .where(Player.game_id == game.id)
            .order_by(Player.score_total.desc())
        ).all()
        if players:
            winner = players[0]
            if winner.name not in winner_counts:
                winner_counts[winner.name] = {"wins": 0, "color": winner.color}
            winner_counts[winner.name]["wins"] += 1

    top_winners = sorted(
        [{"name": name, **data} for name, data in winner_counts.items()],
        key=lambda w: -w["wins"],
    )[:5]

    # Recent games (last 10)
    recent_raw = session.exec(
        select(Game).order_by(Game.created_at.desc()).limit(10)
    ).all()

    recent_games = []
    for game in recent_raw:
        players = session.exec(
            select(Player)
            .where(Player.game_id == game.id)
            .order_by(Player.score_total.desc())
        ).all()
        winner = None
        if game.status == "finished" and players:
            winner = {"name": players[0].name, "score": players[0].score_total, "color": players[0].color}
        recent_games.append({
            "id": game.id,
            "name": game.name,
            "status": game.status,
            "created_at": game.created_at,
            "player_count": len(players),
            "players": [{"name": p.name, "color": p.color, "score": p.score_total} for p in players],
            "winner": winner,
        })

    # Games by week (last 8 weeks)
    all_games = session.exec(
        select(Game).order_by(Game.created_at.desc())
    ).all()

    week_counts: dict[str, int] = {}
    for game in all_games:
        week_key = game.created_at.strftime("%Y-W%W")
        week_counts[week_key] = week_counts.get(week_key, 0) + 1

    games_by_week = [
        {"week": week, "count": count}
        for week, count in sorted(week_counts.items(), reverse=True)[:8]
    ]

    return DashboardStats(
        total_games=total_games,
        finished_games=finished_games,
        active_games=active_games,
        total_actions=total_actions,
        top_winners=top_winners,
        recent_games=recent_games,
        games_by_week=games_by_week,
    )
