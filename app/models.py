"""SQLModel data models for Carcassonne Scoreboard.

The naming convention MUST be set before any model class is defined,
so that Alembic batch mode can reference constraints by name.
"""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

# Set naming convention BEFORE any model class definitions.
# This ensures all constraints (PK, FK, UQ, CK, IX) get deterministic names
# that Alembic batch mode can reference for ALTER TABLE operations.
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

BOARD_SIZE = 50


class Game(SQLModel, table=True):
    __tablename__ = "game"
    __table_args__ = (
        CheckConstraint(
            "status IN ('setup', 'playing', 'scoring', 'finished')",
            name="game_status_check",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str
    status: str = Field(default="setup")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Player(SQLModel, table=True):
    __tablename__ = "player"
    __table_args__ = (
        CheckConstraint(
            "turn_order BETWEEN 1 AND 6",
            name="player_turn_order_range",
        ),
        UniqueConstraint("game_id", "color", name="uq_player_game_color"),
        UniqueConstraint("game_id", "turn_order", name="uq_player_game_turn_order"),
        UniqueConstraint("game_id", "name", name="uq_player_game_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    name: str
    color: str
    score_total: int = Field(default=0)
    turn_order: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def current_cell(self) -> int:
        """Position on the 0-49 scoring track."""
        return self.score_total % BOARD_SIZE

    @property
    def lap(self) -> int:
        """Number of complete laps around the board."""
        return self.score_total // BOARD_SIZE


class ScoreAction(SQLModel, table=True):
    __tablename__ = "score_action"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'ROAD_COMPLETED', 'CITY_COMPLETED', 'MONASTERY_COMPLETED', "
            "'ROAD_FINAL', 'CITY_FINAL', 'MONASTERY_FINAL', "
            "'FARM_FINAL', 'MANUAL')",
            name="score_action_event_type_check",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    event_type: str
    description: str | None = None
    is_undone: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScoreEntry(SQLModel, table=True):
    __tablename__ = "score_entry"
    __table_args__ = (
        UniqueConstraint(
            "action_id", "player_id", name="uq_score_entry_action_player"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    action_id: int = Field(foreign_key="score_action.id")
    player_id: int = Field(foreign_key="player.id")
    points: int
    score_before: int
    score_after: int
