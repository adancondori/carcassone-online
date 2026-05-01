"""Scoring service functions for Carcassonne Scoreboard.

Core operations: add_score, undo_last, rollback_to, recalculate_score.
All functions take a Session as first argument for explicit transaction control.
"""

from sqlmodel import Session

from app.models import ScoreAction


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
    raise NotImplementedError


def undo_last(session: Session, game_id: int) -> ScoreAction | None:
    """Mark the last active ScoreAction as undone and recalculate affected scores.

    Args:
        session: Database session.
        game_id: The game to undo in.

    Returns:
        The undone ScoreAction, or None if no active actions exist.
    """
    raise NotImplementedError


def rollback_to(session: Session, game_id: int, action_id: int) -> int:
    """Mark all active actions after action_id as undone and recalculate scores.

    Args:
        session: Database session.
        game_id: The game to rollback in.
        action_id: The action to rollback to (this action stays active).

    Returns:
        Number of actions that were undone.
    """
    raise NotImplementedError


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
    raise NotImplementedError
