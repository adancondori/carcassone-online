"""Integration tests for the voice endpoint (plan v2, fase 4).

The transcriber is faked via dependency override — no Whisper model needed.
Player colors from the helpers: Alice=blue, Bob=red (add_players order).
"""

import pytest
from sqlmodel import select

from app.main import app
from app.models import VoiceLog
from app.voice.transcriber import get_transcriber

from tests.test_web import (  # reuse existing helpers
    create_game,
    add_players,
    create_started_game,
    post_score,
)


class FakeTranscriber:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def transcribe(self, audio: bytes) -> str:
        self.calls += 1
        return self.text


def set_transcript(text: str) -> FakeTranscriber:
    fake = FakeTranscriber(text)
    app.dependency_overrides[get_transcriber] = lambda: fake
    return fake


def post_voice(client, game_id, audio: bytes = b"fake-audio-bytes"):
    return client.post(
        f"/games/{game_id}/voice",
        files={"audio": ("clip.webm", audio, "audio/webm")},
        headers={"HX-Request": "true"},
    )


def get_logs(session, game_id):
    return session.exec(
        select(VoiceLog).where(VoiceLog.game_id == game_id)
    ).all()


class TestVoiceApplies:
    def test_simple_command_scores_player(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("agrega 5 puntos al rojo")

        resp = post_voice(client, game_id)

        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert 'class="score-value">5</td>' in resp.text
        logs = get_logs(session, game_id)
        assert len(logs) == 1
        assert logs[0].status == "applied"
        assert logs[0].action_id is not None
        assert logs[0].transcript == "agrega 5 puntos al rojo"

    def test_shared_command_with_event_type(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("ciudad 8 al azul y al rojo")

        resp = post_voice(client, game_id)

        assert resp.text.count('class="score-value">8</td>') == 2
        assert "Ciudad" in resp.text  # history shows the event label

    def test_negative_correction(self, client, session):
        game_id, player_ids = create_started_game(client, session)
        post_score(client, game_id, [player_ids[1]], 10)
        set_transcript("quita 3 al rojo")

        resp = post_voice(client, game_id)

        assert 'class="score-value">7</td>' in resp.text

    def test_success_toast_shows_interpretation(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("agrega 5 al rojo")

        resp = post_voice(client, game_id)

        assert 'id="voice-toast"' in resp.text
        assert "+5" in resp.text
        assert "Bob" in resp.text  # rojo → Bob


class TestVoiceErrors:
    def test_parse_error_is_logged_and_shown(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("hola qué tal amigos")

        resp = post_voice(client, game_id)

        assert resp.status_code == 200
        assert "No entendí" in resp.text
        logs = get_logs(session, game_id)
        assert logs[0].status == "parse_error"
        assert logs[0].action_id is None

    def test_color_not_in_game(self, client, session):
        """'rosa' is a valid color but no player has it in this game."""
        game_id, _ = create_started_game(client, session)
        set_transcript("agrega 5 al rosa")

        resp = post_voice(client, game_id)

        assert "rosa" in resp.text
        logs = get_logs(session, game_id)
        assert logs[0].status == "validation_error"

    def test_empty_transcript(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("")

        resp = post_voice(client, game_id)

        assert resp.status_code == 200
        logs = get_logs(session, game_id)
        assert logs[0].status == "empty_audio"

    def test_granja_during_playing_rejected(self, client, session):
        game_id, _ = create_started_game(client, session)
        set_transcript("granja 9 al rojo")

        resp = post_voice(client, game_id)

        assert "Granja" in resp.text
        logs = get_logs(session, game_id)
        assert logs[0].status == "validation_error"

    def test_oversized_clip_rejected_without_transcribing(self, client, session):
        game_id, _ = create_started_game(client, session)
        fake = set_transcript("agrega 5 al rojo")

        resp = post_voice(client, game_id, audio=b"x" * (2 * 1024 * 1024))

        assert resp.status_code == 200
        assert fake.calls == 0
        logs = get_logs(session, game_id)
        assert logs[0].status == "empty_audio"

    def test_nonexistent_game_returns_404(self, client, session):
        set_transcript("agrega 5 al rojo")
        resp = post_voice(client, 9999)
        assert resp.status_code == 404

    def test_setup_game_rejected(self, client, session):
        """Voice scoring only works in playing/scoring states."""
        game_id = create_game(client)
        add_players(client, game_id, count=2)
        set_transcript("agrega 5 al rojo")

        resp = post_voice(client, game_id)

        assert resp.status_code == 200
        logs = get_logs(session, game_id)
        assert logs[0].status == "validation_error"


class TestVoiceUI:
    def test_dashboard_includes_voice_controls(self, client, session):
        """The dashboard ships the voice UI: tabs, mic button, script, toast."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert 'id="voice-mic-btn"' in resp.text
        assert 'class="mode-tab' in resp.text
        assert f'data-game-id="{game_id}"' in resp.text
        assert "voice.js" in resp.text
        assert 'id="voice-toast"' in resp.text

    def test_finished_game_has_no_voice_controls(self, client, session):
        game_id, _ = create_started_game(client, session)
        client.post(f"/games/{game_id}/finish", follow_redirects=False)

        resp = client.get(f"/games/{game_id}")

        assert 'id="voice-mic-btn"' not in resp.text

    def test_game_actions_include_redo_button(self, client, session):
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert f"/games/{game_id}/redo" in resp.text


class TestTableMode:
    def test_dashboard_includes_table_mode_overlay(self, client, session):
        """The dashboard ships the table-mode overlay and its open button."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert 'id="table-mode"' in resp.text
        assert "data-table-mode-open" in resp.text
        assert "data-table-mode-close" in resp.text
        assert 'class="tm-score"' in resp.text

    def test_table_mode_updates_with_fragments(self, client, session):
        """Scoring returns the table-mode overlay as an OOB fragment too."""
        game_id, player_ids = create_started_game(client, session)

        resp = post_score(client, game_id, [player_ids[0]], 12)

        assert 'id="table-mode"' in resp.text
        assert 'class="tm-score">12<' in resp.text

    def test_table_mode_has_mic_in_active_game(self, client, session):
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert "data-voice-mic" in resp.text

    def test_table_mode_has_no_mic_when_finished(self, client, session):
        game_id, _ = create_started_game(client, session)
        client.post(f"/games/{game_id}/finish", follow_redirects=False)

        resp = client.get(f"/games/{game_id}")

        assert 'id="table-mode"' in resp.text
        assert "data-voice-mic" not in resp.text


class TestVoicePanelGrid:
    def test_voice_panel_has_colored_player_cards(self, client, session):
        """The voice tab shows a grid of player-colored cards with big scores."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert 'class="vp-grid"' in resp.text
        assert 'vp-card' in resp.text
        assert 'class="vp-score"' in resp.text
        # Cards carry the player color as background (Alice=blue, Bob=red).
        # The spaced `background: #...` style is unique to the colored cards.
        assert 'style="background: #0055BF"' in resp.text
        assert 'style="background: #CC0000"' in resp.text

    def test_voice_panel_has_maximize_button(self, client, session):
        """Below the grid there is a fullscreen (table mode) button."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert 'class="vp-maximize"' in resp.text

    def test_voice_grid_updates_with_fragments(self, client, session):
        game_id, player_ids = create_started_game(client, session)

        resp = post_score(client, game_id, [player_ids[0]], 12)

        assert 'class="vp-score">12<' in resp.text

    def test_yellow_card_uses_dark_text(self, client, session):
        """Light card colors (yellow/pink) need dark text for contrast."""
        game_id = create_game(client)
        add_players(client, game_id, count=4)  # includes yellow (Diana)
        client.post(f"/games/{game_id}/start", follow_redirects=False)

        resp = client.get(f"/games/{game_id}")

        assert "vp-card pcard-dark" in resp.text


class TestHelpModal:
    def test_dashboard_includes_help_button_and_modal(self, client, session):
        """The dashboard ships an (i) help button and the help modal."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert "data-help-open" in resp.text
        assert 'id="help-modal"' in resp.text

    def test_help_modal_content_is_organized(self, client, session):
        """Help covers: how to speak, what to say, shortcuts, table mode."""
        game_id, _ = create_started_game(client, session)

        resp = client.get(f"/games/{game_id}")

        assert "Cómo hablar" in resp.text
        assert "Qué puedes decir" in resp.text
        assert "Atajos de teclado" in resp.text
        assert "Modo mesa" in resp.text
        # Example commands and key rules present
        assert "agrega 5 puntos al rojo" in resp.text
        assert "Cmd/Ctrl + Shift + Z" in resp.text
