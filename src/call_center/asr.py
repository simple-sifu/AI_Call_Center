"""Speech recognition behind a small ``Transcriber`` interface.

The real backend is faster-whisper on CPU (int8). The model loads lazily on the first
``transcribe`` call and one transcriber is kept per model size for the process.
``load_channels`` decodes the separate channels of a stereo file for speaker labelling.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from threading import Lock
from typing import Protocol

import numpy as np

DUAL_MONO_TOLERANCE = 1e-3
SAMPLE_RATE = 16_000


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


def load_channels(path: str | Path) -> tuple[list[np.ndarray], int, int]:
    """``(channels, rate, source channel count)`` for speaker labelling.

    Stereo gives the left and right channels at 16 kHz. Any other count, or a stereo file
    whose two channels are identical (dual-mono), gives no channels. The count is read
    from the file's audio stream, because ``decode_audio(split_stereo=True)`` upmixes
    mono to two identical channels.
    """
    import av

    # Same leniency as faster-whisper's own decode, so a file it transcribes opens here.
    with av.open(str(path), metadata_errors="ignore") as container:
        count = container.streams.audio[0].channels
    if count != 2:
        return [], SAMPLE_RATE, count

    from faster_whisper import decode_audio

    left, right = decode_audio(str(path), sampling_rate=SAMPLE_RATE, split_stereo=True)
    # Dual-mono: one mix copied to both channels. Lossy codecs (e.g. MP3 joint stereo)
    # leave tiny differences, so compare within about -60 dBFS rather than exactly.
    if (
        left.shape == right.shape
        and np.max(np.abs(left - right), initial=0.0) <= DUAL_MONO_TOLERANCE
    ):
        return [], SAMPLE_RATE, count
    return [left, right], SAMPLE_RATE, count
