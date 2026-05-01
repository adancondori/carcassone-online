"""Shared test fixtures for Carcassonne Scoreboard tests.

Imports app.db to ensure the SQLite pragma event listener is registered
globally before any engine is created.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.db  # noqa: F401 -- registers pragma event listener

from app.db import get_session
from app.main import app
from app.models import Game, Player


@pytest.fixture(name="engine")
def engine_fixture():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    """Database session for a single test, rolled back after use."""
    with Session(engine) as session:
        yield session


@pytest.fixture(name="game_with_players")
def game_with_players_fixture(session):
    """A game in 'playing' status with two players: Alice (blue) and Bob (red)."""
    game = Game(name="Test Game", status="playing")
    session.add(game)
    session.flush()

    alice = Player(
        game_id=game.id, name="Alice", color="blue", turn_order=1
    )
    bob = Player(
        game_id=game.id, name="Bob", color="red", turn_order=2
    )
    session.add(alice)
    session.add(bob)
    session.commit()

    session.refresh(game)
    session.refresh(alice)
    session.refresh(bob)

    return game, [alice, bob]


@pytest.fixture(name="client")
def client_fixture(session):
    """TestClient that uses the test session (in-memory SQLite)."""

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
