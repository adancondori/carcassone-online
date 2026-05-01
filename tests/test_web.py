"""Integration tests for Carcassonne Scoreboard web routes.

Tests cover the complete web flow: game creation, player management,
starting games, scoring (single/shared/cumulative), and undo.
Validates HTMX fragment structure: fragments have no DOCTYPE,
OOB attributes are present, score values are correct.
"""

import pytest
from sqlmodel import select

from app.models import Player


# ── Helpers ─────────────────────────────────────────────────


def create_game(client, name="Test Game"):
    """Create a game via POST and return the game_id."""
    resp = client.post("/games", data={"name": name}, follow_redirects=False)
    assert resp.status_code == 303
    # Location: /games/{id}/setup
    location = resp.headers["location"]
    game_id = int(location.split("/")[2])
    return game_id


def add_players(client, game_id, count=2):
    """Add the specified number of players to a game."""
    colors = ["blue", "red", "green", "yellow", "black", "pink"]
    names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]
    for i in range(count):
        client.post(
            f"/games/{game_id}/players",
            data={"name": names[i], "color": colors[i]},
            follow_redirects=False,
        )


def start_game(client, game_id):
    """Start a game via POST."""
    resp = client.post(
        f"/games/{game_id}/start", follow_redirects=False
    )
    assert resp.status_code == 303


def get_player_ids(session, game_id):
    """Get player IDs from the database, ordered by turn_order."""
    players = session.exec(
        select(Player)
        .where(Player.game_id == game_id)
        .order_by(Player.turn_order)
    ).all()
    return [p.id for p in players]


def create_started_game(client, session, num_players=2):
    """Create a game, add players, start it. Returns (game_id, player_ids)."""
    game_id = create_game(client)
    add_players(client, game_id, count=num_players)
    start_game(client, game_id)
    player_ids = get_player_ids(session, game_id)
    return game_id, player_ids


def post_score(client, game_id, player_ids, points, event_type="CITY_COMPLETED"):
    """Submit a scoring action. Returns the response."""
    data = {
        "player_ids": player_ids,
        "points": str(points),
        "event_type": event_type,
    }
    return client.post(
        f"/games/{game_id}/score",
        data=data,
        headers={"HX-Request": "true"},
    )


def post_undo(client, game_id):
    """Submit an undo action. Returns the response."""
    return client.post(
        f"/games/{game_id}/undo",
        headers={"HX-Request": "true"},
    )


# ── Setup Flow Tests ────────────────────────────────────────


class TestSetupFlow:
    """Tests for game creation and player management."""

    def test_setup_page_renders(self, client):
        """GET /games/new returns 200 with 'Nueva Partida' in HTML."""
        resp = client.get("/games/new")
        assert resp.status_code == 200
        assert "Nueva Partida" in resp.text

    def test_create_game(self, client):
        """POST /games with name returns 303 redirect to /games/{id}/setup."""
        resp = client.post(
            "/games", data={"name": "My Game"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert "/setup" in resp.headers["location"]

    def test_setup_page_shows_players(self, client, session):
        """After adding a player, setup page shows the player name."""
        game_id = create_game(client)
        client.post(
            f"/games/{game_id}/players",
            data={"name": "Alice", "color": "blue"},
            follow_redirects=False,
        )
        resp = client.get(f"/games/{game_id}/setup")
        assert resp.status_code == 200
        assert "Alice" in resp.text

    def test_add_player(self, client):
        """POST /games/{id}/players with name and color returns 303."""
        game_id = create_game(client)
        resp = client.post(
            f"/games/{game_id}/players",
            data={"name": "Alice", "color": "blue"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_remove_player(self, client, session):
        """After removing a player, they no longer appear on setup page."""
        game_id = create_game(client)
        client.post(
            f"/games/{game_id}/players",
            data={"name": "Alice", "color": "blue"},
            follow_redirects=False,
        )
        pids = get_player_ids(session, game_id)
        assert len(pids) == 1

        resp = client.post(
            f"/games/{game_id}/players/{pids[0]}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Verify player is gone
        resp = client.get(f"/games/{game_id}/setup")
        assert "Alice" not in resp.text

    def test_start_game(self, client):
        """With 2 players, POST /games/{id}/start returns 303 to dashboard."""
        game_id = create_game(client)
        add_players(client, game_id, count=2)
        resp = client.post(
            f"/games/{game_id}/start", follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/games/{game_id}"

    def test_start_game_requires_min_players(self, client, session):
        """With only 1 player, starting fails and game stays in setup."""
        game_id = create_game(client)
        add_players(client, game_id, count=1)
        resp = client.post(
            f"/games/{game_id}/start", follow_redirects=False
        )
        assert resp.status_code == 303
        # Should redirect back to setup, not dashboard
        assert "/setup" in resp.headers["location"]


# ── Dashboard Tests ─────────────────────────────────────────


class TestDashboard:
    """Tests for the game dashboard page."""

    def test_dashboard_renders_full_page(self, client, session):
        """GET /games/{id} for a started game returns full HTML page."""
        game_id, _ = create_started_game(client, session)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" in resp.text
        assert "score-table" in resp.text

    def test_dashboard_shows_all_players(self, client, session):
        """Dashboard shows all player names."""
        game_id, _ = create_started_game(client, session, num_players=3)
        resp = client.get(f"/games/{game_id}")
        assert "Alice" in resp.text
        assert "Bob" in resp.text
        assert "Charlie" in resp.text

    def test_dashboard_redirects_setup_if_not_started(self, client):
        """GET /games/{id} when status=setup redirects to setup page."""
        game_id = create_game(client)
        resp = client.get(f"/games/{game_id}", follow_redirects=False)
        assert resp.status_code == 303
        assert "/setup" in resp.headers["location"]


# ── Scoring Tests ───────────────────────────────────────────


class TestScoring:
    """Tests for the scoring endpoint and HTMX fragment responses."""

    def test_score_returns_fragments(self, client, session):
        """POST /score returns HTML fragment without DOCTYPE (not full page)."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 8)
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text

    def test_score_contains_score_table(self, client, session):
        """POST /score response contains the score-table div."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 5)
        assert "score-table" in resp.text

    def test_score_contains_oob_fragments(self, client, session):
        """POST /score response contains hx-swap-oob attributes."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 5)
        assert 'hx-swap-oob="true"' in resp.text

    def test_score_updates_player_total(self, client, session):
        """Scoring 12 points shows '12' in the response."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 12)
        # The score-value cell should contain 12
        assert ">12<" in resp.text

    def test_score_shared(self, client, session):
        """Scoring 10 points to 2 players shows '10' for both."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0], pids[1]], 10)
        # Both players should have 10 in their score-value cells
        # Count occurrences of ">10<" in score values
        assert resp.text.count(">10<") >= 2

    def test_score_cumulative(self, client, session):
        """Scoring 8 then 12 shows cumulative total of 20."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 8)
        resp = post_score(client, game_id, [pids[0]], 12)
        assert ">20<" in resp.text


# ── Undo Tests ──────────────────────────────────────────────


class TestUndo:
    """Tests for the undo endpoint and fragment responses."""

    def test_undo_returns_fragments(self, client, session):
        """POST /undo returns HTML fragments with OOB attributes."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 5)
        resp = post_undo(client, game_id)
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert 'hx-swap-oob="true"' in resp.text

    def test_undo_reverts_score(self, client, session):
        """Score 8 then undo shows score back to 0."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 8)
        resp = post_undo(client, game_id)
        # Both players should show 0
        assert resp.text.count(">0<") >= 2

    def test_undo_shared_action(self, client, session):
        """Score shared 10 to 2 players, undo, both show 0."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0], pids[1]], 10)
        resp = post_undo(client, game_id)
        # Both scores should be back to 0
        assert resp.text.count(">0<") >= 2

    def test_undo_nothing(self, client, session):
        """Undo with no actions returns fragments with 0 scores."""
        game_id, pids = create_started_game(client, session)
        resp = post_undo(client, game_id)
        assert resp.status_code == 200
        assert "score-table" in resp.text
        # Both players have 0 scores
        assert resp.text.count(">0<") >= 2
