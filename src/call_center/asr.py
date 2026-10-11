"""Speech recognition behind a small ``Transcriber`` interface.

The real backend is faster-whisper on CPU (int8). The model loads lazily on the first
``transcribe`` call and one transcriber is kept per model size for the process.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from threading import Lock
from typing import Protocol


@dataclass(frozen=True)
class RawSegment:
    start: float
    end: float
    text: str


class Transcriber(Protocol):
    def transcribe(self, path: str | Path) -> list[RawSegment]: ...


class FasterWhisperTranscriber:
    def __init__(self, model_size: str) -> None:
        self.model_size = model_size
        self._model = None
        self._lock = Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, path: str | Path) -> list[RawSegment]:
        segments, _info = self._load().transcribe(str(path))
        return [RawSegment(start=s.start, end=s.end, text=s.text.strip()) for s in segments]


@cache
def get_transcriber(model_size: str) -> Transcriber:
    """The process-wide transcriber for ``model_size``."""
    return FasterWhisperTranscriber(model_size)
