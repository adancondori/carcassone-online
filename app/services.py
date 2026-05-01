"""Scoring service functions for Carcassonne Scoreboard.

Core operations: add_score, undo_last, rollback_to, recalculate_score.
All functions take a Session as first argument for explicit transaction control.
"""

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Player, ScoreAction, ScoreEntry


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
