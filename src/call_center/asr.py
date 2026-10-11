"""Speech recognition behind a small ``Transcriber`` interface.

The real backend is faster-whisper on CPU (int8). The model loads lazily on the first
``transcribe`` call and one transcriber is kept per model size for the process.
``load_channels`` streams a per-10 ms channel loudness envelope for speaker labelling.
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


def _valid_frames(frames):
    """Skip frames PyAV cannot decode, matching faster-whisper's ``decode_audio``."""
    import av

    iterator = iter(frames)
    while True:
        try:
            yield next(iterator)
        except StopIteration:
            return
        except av.error.InvalidDataError:
            continue


ENVELOPE_RATE = 100  # windows per second: 10 ms RMS windows
_WINDOW = SAMPLE_RATE // ENVELOPE_RATE


def load_channels(path: str | Path) -> tuple[list[np.ndarray], int, int]:
    """``(channels, rate, source channel count)`` for speaker labelling.

    Stereo gives a per-10 ms RMS envelope for the left and right channels at
    ``ENVELOPE_RATE``. RMS over a span of equal-size window RMS values equals the
    sample RMS, so ``speakers.label_segments`` gets the answer it would from the raw
    16 kHz samples up to 10 ms boundary rounding, without the whole file ever being held
    in memory. Corrupt frames are skipped, as faster-whisper's own decode skips them. Any other
    count, or a stereo file whose two channels are identical (dual-mono), gives no
    channels. The count is read from the file's audio stream, because a stereo decode
    upmixes mono to two identical channels.
    """
    import av

    # Same leniency as faster-whisper's own decode, so a file it transcribes opens here.
    with av.open(str(path), metadata_errors="ignore") as container:
        stream = container.streams.audio[0]
        count = stream.channels
        if count != 2:
            return [], ENVELOPE_RATE, count
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
        squares: list[np.ndarray] = []  # per window: [left, right] mean square
        carry = np.zeros((2, 0), dtype=np.float32)
        max_diff = 0.0

        def consume(frames) -> None:
            nonlocal carry, max_diff
            for frame in frames:
                samples = frame.to_ndarray().astype(np.float32, copy=False)
                if samples.size:
                    max_diff = max(max_diff, float(np.max(np.abs(samples[0] - samples[1]))))
                carry = np.concatenate([carry, samples], axis=1)
                whole = carry.shape[1] // _WINDOW * _WINDOW
                if whole:
                    block = carry[:, :whole].reshape(2, -1, _WINDOW)
                    squares.append(np.mean(np.square(block, dtype=np.float64), axis=2).T)
                    carry = carry[:, whole:]

        for frame in _valid_frames(container.decode(stream)):
            consume(resampler.resample(frame))
        consume(resampler.resample(None))
    if carry.shape[1]:  # trailing partial window
        squares.append(np.mean(np.square(carry, dtype=np.float64), axis=1)[None, :])

    # Dual-mono: one mix copied to both channels. Lossy codecs (e.g. MP3 joint stereo)
    # leave tiny differences, so compare within about -60 dBFS rather than exactly.
    if max_diff <= DUAL_MONO_TOLERANCE:
        return [], ENVELOPE_RATE, count
    envelope = np.sqrt(np.concatenate(squares)) if squares else np.zeros((0, 2))
    return [envelope[:, 0], envelope[:, 1]], ENVELOPE_RATE, count
