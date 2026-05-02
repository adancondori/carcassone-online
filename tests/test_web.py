"""Integration tests for Carcassonne Scoreboard web routes.

Tests cover the complete web flow: game creation, player management,
starting games, scoring (single/shared/cumulative), and undo.
Validates HTMX fragment structure: fragments have no DOCTYPE,
OOB attributes are present, score values are correct.
"""

import pytest
from sqlmodel import select

from app.models import Game, Player, ScoreAction


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


def post_rollback(client, game_id, action_id):
    """Submit a rollback action. Returns the response."""
    return client.post(
        f"/games/{game_id}/rollback",
        data={"action_id": str(action_id)},
        headers={"HX-Request": "true"},
    )


def get_action_ids(session, game_id):
    """Get action IDs from the database, ordered by id."""
    actions = session.exec(
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .order_by(ScoreAction.id)
    ).all()
    return [a.id for a in actions]


def begin_scoring(client, game_id):
    """Transition game to scoring state via POST."""
    resp = client.post(f"/games/{game_id}/begin-scoring", follow_redirects=False)
    assert resp.status_code == 303


def finish_game(client, game_id):
    """Transition game to finished state via POST."""
    resp = client.post(f"/games/{game_id}/finish", follow_redirects=False)
    assert resp.status_code == 303


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


# ── History Tests ──────────────────────────────────────────


class TestHistory:
    """Tests for the history panel display and OOB fragment (DISPLAY-03, UNDO-03)."""

    def test_score_response_includes_history(self, client, session):
        """POST /score response includes the history OOB fragment (DISPLAY-03)."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 5)
        assert resp.status_code == 200
        assert 'id="history"' in resp.text
        assert 'hx-swap-oob="true"' in resp.text

    def test_history_shows_event_type_label(self, client, session):
        """History displays localized event type labels (DISPLAY-03)."""
        game_id, pids = create_started_game(client, session)
        # Score with CITY_COMPLETED
        resp = post_score(client, game_id, [pids[0]], 8, event_type="CITY_COMPLETED")
        assert "Ciudad" in resp.text

        # Score with ROAD_COMPLETED
        resp = post_score(client, game_id, [pids[0]], 3, event_type="ROAD_COMPLETED")
        assert "Camino" in resp.text

    def test_history_shows_player_names_and_points(self, client, session):
        """History shows player name and point value for each action."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 8)
        assert "Alice" in resp.text
        assert "+8" in resp.text

    def test_history_shows_shared_scoring(self, client, session):
        """History shows all players involved in a shared scoring action."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0], pids[1]], 12)
        assert "Alice" in resp.text
        assert "Bob" in resp.text
        assert "+12" in resp.text

    def test_undo_marks_action_as_undone_in_history(self, client, session):
        """Undo response marks the action with 'undone' class in history (UNDO-03)."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 5)
        resp = post_undo(client, game_id)
        assert resp.status_code == 200
        # The history item should have the 'undone' class
        assert "undone" in resp.text

    def test_dashboard_full_page_includes_history(self, client, session):
        """GET /games/{id} for a started game includes the history panel."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 7)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        assert 'id="history"' in resp.text
        assert "Alice" in resp.text
        assert "+7" in resp.text


# ── Rollback Tests ─────────────────────────────────────────


class TestRollback:
    """Tests for the rollback endpoint (UNDO-02, UNDO-04)."""

    def test_rollback_returns_fragments(self, client, session):
        """POST /rollback returns HTML fragments with OOB attributes (UNDO-02)."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 5)
        post_score(client, game_id, [pids[0]], 3)
        action_ids = get_action_ids(session, game_id)
        resp = post_rollback(client, game_id, action_ids[0])
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert 'hx-swap-oob="true"' in resp.text

    def test_rollback_reverts_scores(self, client, session):
        """Rollback to action 1 keeps its score, removes action 2 (UNDO-04)."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 8)   # action 1: Alice = 8
        post_score(client, game_id, [pids[0]], 10)  # action 2: Alice = 18
        action_ids = get_action_ids(session, game_id)
        resp = post_rollback(client, game_id, action_ids[0])
        # Alice should be back to 8 (action 1 active, action 2 undone).
        # Match score table cells only — board SVG debug labels also contain ">N<".
        tb_start = resp.text.find('id="score-table"')
        assert tb_start != -1
        tb_end = resp.text.find("</table>", tb_start)
        score_table_html = resp.text[tb_start:tb_end]
        assert 'class="score-value">8</td>' in score_table_html
        assert 'class="score-value">18</td>' not in score_table_html

    def test_rollback_marks_subsequent_actions_undone(self, client, session):
        """Rollback to action 1 marks actions 2 and 3 as undone (UNDO-02)."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 3)  # action 1
        post_score(client, game_id, [pids[0]], 4)  # action 2
        post_score(client, game_id, [pids[0]], 5)  # action 3
        action_ids = get_action_ids(session, game_id)
        resp = post_rollback(client, game_id, action_ids[0])

        # Extract the history section from the response
        text = resp.text
        history_start = text.find('id="history"')
        assert history_start != -1, "History section not found in response"
        history_section = text[history_start:]

        # Actions 2 and 3 should be marked as undone in the history
        # Count 'undone' occurrences in history (should be 2 for actions 2 and 3)
        assert history_section.count("undone") >= 2

        # Action 1 should still be active (its history-item should NOT have undone class)
        # Find action 1's entry: it has the lowest action id
        action1_marker = f"#{action_ids[0]}"
        action1_pos = history_section.find(action1_marker)
        assert action1_pos != -1, f"Action #{action_ids[0]} not found in history"

        # Check the list item containing action 1 does NOT have 'undone' class
        # The li tag is before the action number marker
        li_start = history_section.rfind("<li", 0, action1_pos)
        li_fragment = history_section[li_start:action1_pos]
        assert "undone" not in li_fragment, "Action 1 should NOT be marked as undone"

    def test_rollback_shared_action(self, client, session):
        """Rollback with shared scoring keeps shared action active (UNDO-04)."""
        game_id, pids = create_started_game(client, session)
        # Action 1: 10 points to both players
        post_score(client, game_id, [pids[0], pids[1]], 10)
        # Action 2: 5 points to Alice only
        post_score(client, game_id, [pids[0]], 5)
        action_ids = get_action_ids(session, game_id)
        resp = post_rollback(client, game_id, action_ids[0])
        # Both players should have 10 (action 1 stays active)
        assert resp.text.count(">10<") >= 2
        # Only action 2 should be undone (1 occurrence of undone in history)
        history_start = resp.text.find('id="history"')
        history_section = resp.text[history_start:]
        assert history_section.count("undone") == 1

    def test_rollback_nothing_when_last_action(self, client, session):
        """Rollback to the only action does nothing (no subsequent actions)."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 7)
        action_ids = get_action_ids(session, game_id)
        resp = post_rollback(client, game_id, action_ids[0])
        assert resp.status_code == 200
        # Score should be unchanged (7)
        assert ">7<" in resp.text
        # No actions should be marked as undone
        history_start = resp.text.find('id="history"')
        history_section = resp.text[history_start:]
        assert "undone" not in history_section


# ── Board Tests ───────────────────────────────────────────


class TestBoardContext:
    """Unit tests for build_board_context helper (BOARD-01)."""

    def test_empty_players(self):
        """build_board_context with empty list returns empty dict."""
        from app.web.dependencies import build_board_context

        result = build_board_context([])
        assert result == {}

    def test_single_player_at_zero(self, session):
        """Single player at score 0 maps to cell 0 with correct coords."""
        from app.web.dependencies import BOARD_CELLS, build_board_context

        game = Game(name="Test", status="playing")
        session.add(game)
        session.flush()
        player = Player(
            game_id=game.id, name="Alice", color="blue",
            turn_order=1, score_total=0,
        )
        session.add(player)
        session.commit()
        session.refresh(player)

        result = build_board_context([player])
        assert 0 in result
        tokens = result[0]
        assert len(tokens) == 1
        t = tokens[0]
        # No stacking offset for single player
        assert t["cx"] == BOARD_CELLS[0][0]
        assert t["cy"] == BOARD_CELLS[0][1]
        assert t["hex"] == "#0055BF"  # blue
        assert t["color"] == "blue"
        assert t["initial"] == "A"
        assert t["lap"] == 0

    def test_player_with_lap(self, session):
        """Player at score 55 maps to cell 5 with lap 1."""
        from app.web.dependencies import BOARD_CELLS, build_board_context

        game = Game(name="Test", status="playing")
        session.add(game)
        session.flush()
        player = Player(
            game_id=game.id, name="Bob", color="red",
            turn_order=1, score_total=55,
        )
        session.add(player)
        session.commit()
        session.refresh(player)

        result = build_board_context([player])
        assert 5 in result  # 55 % 50 = 5
        t = result[5][0]
        assert t["cx"] == BOARD_CELLS[5][0]
        assert t["cy"] == BOARD_CELLS[5][1]
        assert t["lap"] == 1  # 55 // 50 = 1

    def test_stacking_offsets(self, session):
        """Two players at same score get different positions via stacking."""
        from app.web.dependencies import build_board_context

        game = Game(name="Test", status="playing")
        session.add(game)
        session.flush()
        alice = Player(
            game_id=game.id, name="Alice", color="blue",
            turn_order=1, score_total=0,
        )
        bob = Player(
            game_id=game.id, name="Bob", color="red",
            turn_order=2, score_total=0,
        )
        session.add_all([alice, bob])
        session.commit()
        session.refresh(alice)
        session.refresh(bob)

        result = build_board_context([alice, bob])
        assert 0 in result
        tokens = result[0]
        assert len(tokens) == 2
        # Stacking offsets must produce different coordinates
        assert tokens[0]["cx"] != tokens[1]["cx"] or tokens[0]["cy"] != tokens[1]["cy"]

    def test_score_cells_36_and_37_match_track_photo(self):
        """Cells 36 and 37 align with printed numbers on the board image."""
        from app.web.dependencies import BOARD_CELLS

        assert BOARD_CELLS[36] == (135, 156)
        assert BOARD_CELLS[37] == (119, 190)


class TestBoard:
    """Integration tests for the SVG board in dashboard and OOB fragments."""

    def test_dashboard_includes_board_svg(self, client, session):
        """GET /games/{id} includes board SVG with correct structure."""
        game_id, _ = create_started_game(client, session)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        assert 'id="board"' in resp.text
        assert 'class="board-svg"' in resp.text
        assert 'viewBox="0 0 600 420"' in resp.text
        assert "/static/images/carcassonneok.jpg" in resp.text

    def test_score_returns_board_oob(self, client, session):
        """POST /score returns board OOB fragment with token for scored player."""
        game_id, pids = create_started_game(client, session)
        resp = post_score(client, game_id, [pids[0]], 8)
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text

        # Board OOB fragment present
        board_start = resp.text.find('id="board"')
        assert board_start != -1
        board_section = resp.text[board_start:]
        assert 'hx-swap-oob="true"' in resp.text
        # Token should be present for the scored player
        assert "token-meeple" in board_section

    def test_undo_returns_board_oob(self, client, session):
        """POST /undo returns board OOB fragment with updated token positions."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 10)
        resp = post_undo(client, game_id)
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text

        # Board OOB fragment present
        assert 'id="board"' in resp.text
        assert 'hx-swap-oob="true"' in resp.text

    def test_lap_badge_appears(self, client, session):
        """Scoring past 49 produces a lap badge in the board."""
        game_id, pids = create_started_game(client, session)
        # Score 55 points to trigger lap 1
        resp = post_score(client, game_id, [pids[0]], 55)
        assert resp.status_code == 200
        assert "lap-badge" in resp.text
        assert "x1" in resp.text

    def test_stacking_in_board_fragment(self, client, session):
        """Two players with same score produce two tokens in board fragment."""
        game_id, pids = create_started_game(client, session)
        # Score both players same points via shared scoring
        resp = post_score(client, game_id, [pids[0], pids[1]], 10)
        assert resp.status_code == 200
        # Board section should have two token-meeple groups
        board_start = resp.text.find('id="board"')
        board_section = resp.text[board_start:]
        assert board_section.count("token-meeple") == 2


# ── Game States Tests ────────────────────────────────────────


class TestGameStates:
    """Tests for game state transitions, event type filtering, and finished state."""

    # ── State transition tests ──

    def test_begin_scoring_redirect(self, client, session):
        """POST /begin-scoring returns 303 redirect to dashboard."""
        game_id, _ = create_started_game(client, session)
        resp = client.post(f"/games/{game_id}/begin-scoring", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/games/{game_id}"

    def test_begin_scoring_dashboard_shows_scoring_status(self, client, session):
        """After begin_scoring, GET dashboard contains 'Puntuacion final' in header-status."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        assert "Puntuacion final" in resp.text

    def test_finish_game_redirect(self, client, session):
        """POST /finish returns 303 redirect to dashboard."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        resp = client.post(f"/games/{game_id}/finish", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/games/{game_id}"

    def test_finish_game_dashboard_shows_finished(self, client, session):
        """After finish_game, GET dashboard contains 'Finalizada'."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        assert "Finalizada" in resp.text

    # ── Event type filtering tests ──

    def test_playing_shows_completed_event_types(self, client, session):
        """Dashboard in playing state contains CITY_COMPLETED and not CITY_FINAL or FARM_FINAL."""
        game_id, _ = create_started_game(client, session)
        resp = client.get(f"/games/{game_id}")
        assert "CITY_COMPLETED" in resp.text
        assert "CITY_FINAL" not in resp.text
        assert "FARM_FINAL" not in resp.text

    def test_scoring_shows_final_event_types(self, client, session):
        """Dashboard in scoring state contains CITY_FINAL and FARM_FINAL and not CITY_COMPLETED."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "CITY_FINAL" in resp.text
        assert "FARM_FINAL" in resp.text
        assert "CITY_COMPLETED" not in resp.text

    def test_manual_available_in_both_states(self, client, session):
        """Both playing and scoring dashboards contain MANUAL."""
        game_id, _ = create_started_game(client, session)
        # Playing state
        resp = client.get(f"/games/{game_id}")
        assert "MANUAL" in resp.text
        # Scoring state
        begin_scoring(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "MANUAL" in resp.text

    # ── Finished state tests ──

    def test_finished_no_controls(self, client, session):
        """Dashboard in finished state does NOT contain score-form."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert 'id="score-form"' not in resp.text

    def test_finished_no_undo_button(self, client, session):
        """Dashboard in finished state does NOT contain 'Deshacer'."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "Deshacer" not in resp.text

    def test_finished_shows_results_banner(self, client, session):
        """Dashboard in finished state contains 'Partida finalizada'."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "Partida finalizada" in resp.text

    def test_finished_shows_new_game_link(self, client, session):
        """Dashboard in finished state contains '/games/new'."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "/games/new" in resp.text

    def test_finished_still_shows_score_table(self, client, session):
        """Dashboard in finished state contains score-table."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "score-table" in resp.text

    def test_finished_history_no_rollback(self, client, session):
        """Finished dashboard history does NOT contain rollback buttons."""
        game_id, pids = create_started_game(client, session)
        post_score(client, game_id, [pids[0]], 5)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "history-rollback-btn" not in resp.text

    # ── Transition button tests ──

    def test_playing_shows_begin_scoring_button(self, client, session):
        """Dashboard in playing state contains begin-scoring form action."""
        game_id, _ = create_started_game(client, session)
        resp = client.get(f"/games/{game_id}")
        assert "begin-scoring" in resp.text

    def test_scoring_shows_finish_button(self, client, session):
        """Dashboard in scoring state contains /finish form action."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "/finish" in resp.text

    def test_finished_no_transition_button(self, client, session):
        """Dashboard in finished state does NOT contain btn-transition."""
        game_id, _ = create_started_game(client, session)
        begin_scoring(client, game_id)
        finish_game(client, game_id)
        resp = client.get(f"/games/{game_id}")
        assert "btn-transition" not in resp.text

    # ── Scoring in correct state tests ──

    def test_score_with_final_type_in_scoring_state(self, client, session):
        """Scoring with CITY_FINAL in scoring state succeeds."""
        game_id, pids = create_started_game(client, session)
        begin_scoring(client, game_id)
        resp = post_score(client, game_id, [pids[0]], 10, event_type="CITY_FINAL")
        assert resp.status_code == 200
        assert ">10<" in resp.text

    def test_score_with_completed_type_in_scoring_state_rejected(self, client, session):
        """Scoring with CITY_COMPLETED in scoring state is rejected (score stays at baseline)."""
        game_id, pids = create_started_game(client, session)
        begin_scoring(client, game_id)
        # First, establish a baseline score with a valid final type
        post_score(client, game_id, [pids[0]], 10, event_type="CITY_FINAL")
        # Now try scoring with a playing-only type -- should be rejected
        resp = post_score(client, game_id, [pids[0]], 5, event_type="CITY_COMPLETED")
        # Score should remain at 10, not 15
        tb_start = resp.text.find('id="score-table"')
        assert tb_start != -1
        tb_end = resp.text.find("</table>", tb_start)
        score_table_html = resp.text[tb_start:tb_end]
        assert 'class="score-value">10</td>' in score_table_html
        assert 'class="score-value">15</td>' not in score_table_html
