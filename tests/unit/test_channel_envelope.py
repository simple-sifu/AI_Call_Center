"""``asr.load_channels`` streams a per-10 ms RMS envelope instead of decoding whole files."""

import tracemalloc
import wave
from pathlib import Path

import numpy as np
import pytest
from faster_whisper import decode_audio

from call_center import asr

CALL = Path(__file__).parent.parent / "fixtures" / "call_stereo.wav"


@pytest.mark.parametrize("window", [(0.0, 1.0), (2.37, 5.0), (8.0, 12.5)])
def test_envelope_rms_equals_sample_rms(window):
    channels, rate, count = asr.load_channels(CALL)
    assert (rate, count) == (asr.ENVELOPE_RATE, 2)
    full = decode_audio(str(CALL), sampling_rate=asr.SAMPLE_RATE, split_stereo=True)
    start, end = window
    for envelope, samples in zip(channels, full, strict=True):
        a, b = int(start * asr.SAMPLE_RATE), int(end * asr.SAMPLE_RATE)
        true = np.sqrt(np.mean(np.square(samples[a:b], dtype=np.float64)))
        env = np.sqrt(np.mean(np.square(envelope[int(start * rate) : int(end * rate)])))
        assert env == pytest.approx(true, rel=1e-3, abs=1e-6)


def test_stereo_is_never_held_in_memory_whole(tmp_path):
    rate, seconds = asr.SAMPLE_RATE, 180
    path = tmp_path / "long.wav"
    rng = np.random.default_rng(0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for _ in range(seconds):
            w.writeframes((rng.standard_normal((rate, 2)) * [3000, 1000]).astype(np.int16))
    full_float_bytes = seconds * rate * 2 * 4
    tracemalloc.start()
    try:
        channels, _, _ = asr.load_channels(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(channels[0]) == seconds * asr.ENVELOPE_RATE
    assert peak < full_float_bytes / 4


def test_corrupt_frames_are_skipped_like_faster_whisper(monkeypatch):
    import av

    real_decode = av.container.InputContainer.decode

    def flaky(self, *streams):
        for i, frame in enumerate(real_decode(self, *streams)):
            if i == 3:
                raise av.error.InvalidDataError(1094995529, "corrupt frame")
            yield frame

    full = len(asr.load_channels(CALL)[0][0])
    monkeypatch.setattr(av.container.InputContainer, "decode", flaky)
    channels, rate, count = asr.load_channels(CALL)
    assert count == 2 and len(channels) == 2
    assert 0 < len(channels[0]) < full  # the corrupt frame was hit, and did not raise
