"""Tests for the Whisper transcriber wrapper (plan v2, fase 3).

Fast tests cover config and lazy loading. The real transcription test is
marked `slow`: it downloads the Whisper model on first run and needs the
macOS `say` command to synthesize a Spanish audio fixture.
"""

import shutil
import subprocess

import pytest

from app.config import settings
from app.voice.parser import parse_command
from app.voice.transcriber import FasterWhisperTranscriber, get_transcriber


class TestConfig:
    def test_whisper_settings_defaults(self):
        assert settings.whisper_model == "small"
        assert settings.whisper_device == "cpu"
        assert settings.whisper_compute == "int8"
        assert settings.voice_language == "es"


class TestLazyLoading:
    def test_model_not_loaded_on_init(self):
        """Creating the transcriber must be cheap; the model loads on first use."""
        transcriber = FasterWhisperTranscriber()
        assert transcriber._model is None

    def test_get_transcriber_returns_singleton(self):
        assert get_transcriber() is get_transcriber()


def _spanish_voice() -> str | None:
    """Find an installed Spanish voice for the macOS `say` command.

    Prefers the high-quality system voices; novelty voices (Eddy, Grandma…)
    produce audio that Whisper mis-hears.
    """
    if shutil.which("say") is None:
        return None
    result = subprocess.run(
        ["say", "-v", "?"], capture_output=True, text=True, check=False
    )
    spanish = [line for line in result.stdout.splitlines() if " es_" in line]
    for preferred in ("Mónica", "Monica", "Paulina"):
        for line in spanish:
            if line.startswith(preferred):
                return preferred
    return spanish[0].split()[0] if spanish else None


@pytest.mark.slow
class TestRealTranscription:
    def test_transcribes_spanish_command_end_to_end(self, tmp_path):
        """Synthesized audio → Whisper → parser. The full fase 1-3 pipeline."""
        voice = _spanish_voice()
        if voice is None:
            pytest.skip("No Spanish `say` voice available on this machine")

        wav = tmp_path / "command.wav"
        subprocess.run(
            [
                "say", "-v", voice, "agrega cinco puntos al rojo",
                "-o", str(wav), "--data-format=LEI16@16000",
            ],
            check=True,
        )

        transcriber = FasterWhisperTranscriber()
        text = transcriber.transcribe(wav.read_bytes())

        assert "rojo" in text.lower()
        cmd = parse_command(text)
        assert cmd.entries == [("rojo", 5)]
