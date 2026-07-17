"""Audio → text via faster-whisper (plan v2, fase 3).

Port/adapter seam: `Transcriber` is the interface the rest of the app
depends on. `FasterWhisperTranscriber` is the v1 implementation; swapping
to another engine (Whisper API, Vosk, GPU) means writing a new class —
parser, routes and tests don't change. Tests inject a fake via FastAPI
dependency override on `get_transcriber`.
"""

import io
import threading
from typing import Protocol

from app.config import settings

# Bias Whisper toward the command vocabulary (colors, event words, verbs).
VOCABULARY_PROMPT = (
    "Comandos de puntuación de Carcassonne: agrega, suma, anota, quita, "
    "resta puntos; camino, ciudad, monasterio, granja; "
    "rojo, azul, verde, amarillo, negro, rosa."
)


class Transcriber(Protocol):
    """Anything that turns an audio clip into text."""

    def transcribe(self, audio: bytes) -> str: ...


class FasterWhisperTranscriber:
    """Transcribes short clips with a locally-run Whisper model.

    The model loads lazily on first use (startup stays fast) and
    transcriptions are serialized with a lock: they are CPU-bound, so
    running them concurrently would slow every request down.
    """

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
    ):
        self.model_size = model_size or settings.whisper_model
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute
        self.language = language or settings.voice_language
        self._model = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    self._model = WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                    )
        return self._model

    def transcribe(self, audio: bytes) -> str:
        model = self._get_model()
        with self._lock:
            segments, _info = model.transcribe(
                io.BytesIO(audio),
                language=self.language,
                vad_filter=True,
                initial_prompt=VOCABULARY_PROMPT,
                beam_size=5,
            )
            return " ".join(s.text.strip() for s in segments).strip()


_default_transcriber: FasterWhisperTranscriber | None = None


def get_transcriber() -> Transcriber:
    """FastAPI dependency. Tests override this to inject a fake."""
    global _default_transcriber
    if _default_transcriber is None:
        _default_transcriber = FasterWhisperTranscriber()
    return _default_transcriber
