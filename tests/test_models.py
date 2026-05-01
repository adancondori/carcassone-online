"""Tests for SQLModel data models: computed properties and constraint enforcement."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Game, Player, ScoreAction, ScoreEntry


# --- Player computed properties ---


def test_player_cell_zero():
    player = Player(game_id=1, name="X", color="x", turn_order=1, score_total=0)
    assert player.current_cell == 0
    assert player.lap == 0


def test_player_cell_mid():
    player = Player(game_id=1, name="X", color="x", turn_order=1, score_total=27)
    assert player.current_cell == 27
    assert player.lap == 0


def test_player_cell_one_lap():
    player = Player(game_id=1, name="X", color="x", turn_order=1, score_total=53)
    assert player.current_cell == 3
    assert player.lap == 1


def test_player_cell_three_laps():
    player = Player(game_id=1, name="X", color="x", turn_order=1, score_total=152)
    assert player.current_cell == 2
    assert player.lap == 3


def test_player_cell_exact_lap():
    player = Player(game_id=1, name="X", color="x", turn_order=1, score_total=50)
    assert player.current_cell == 0
    assert player.lap == 1


# --- Constraint enforcement ---


def test_game_status_constraint(engine):
    """CHECK constraint rejects invalid game status values."""
    with Session(engine) as session:
        game = Game(name="Bad", status="invalid_status")
        session.add(game)
        with pytest.raises(IntegrityError):
            session.commit()


def test_player_turn_order_range(engine):
    """CHECK constraint rejects turn_order outside 1-6."""
    with Session(engine) as session:
        game = Game(name="Test", status="setup")
        session.add(game)
        session.flush()

        player = Player(
            game_id=game.id, name="X", color="blue", turn_order=7
        )
        session.add(player)
        with pytest.raises(IntegrityError):
            session.commit()


def test_player_unique_color_per_game(game_with_players, session):
    """UNIQUE constraint prevents duplicate color within a game."""
    game, players = game_with_players
    duplicate = Player(
        game_id=game.id, name="Charlie", color="blue", turn_order=3
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()


def test_player_unique_name_per_game(game_with_players, session):
    """UNIQUE constraint prevents duplicate name within a game."""
    game, players = game_with_players
    duplicate = Player(
        game_id=game.id, name="Alice", color="green", turn_order=3
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_key_enforcement(engine):
    """PRAGMA foreign_keys=ON rejects player with nonexistent game_id."""
    with Session(engine) as session:
        player = Player(
            game_id=9999, name="Ghost", color="white", turn_order=1
        )
        session.add(player)
        with pytest.raises(IntegrityError):
            session.commit()


def test_score_entry_unique_action_player(engine):
    """UNIQUE constraint prevents duplicate (action_id, player_id) pairs."""
    with Session(engine) as session:
        game = Game(name="Test", status="playing")
        session.add(game)
        session.flush()

        player = Player(
            game_id=game.id, name="Alice", color="blue", turn_order=1
        )
        session.add(player)
        session.flush()

        action = ScoreAction(
            game_id=game.id, event_type="ROAD_COMPLETED"
        )
        session.add(action)
        session.flush()

        entry1 = ScoreEntry(
            action_id=action.id,
            player_id=player.id,
            points=5,
            score_before=0,
            score_after=5,
        )
        entry2 = ScoreEntry(
            action_id=action.id,
            player_id=player.id,
            points=3,
            score_before=5,
            score_after=8,
        )
        session.add(entry1)
        session.add(entry2)
        with pytest.raises(IntegrityError):
            session.commit()
