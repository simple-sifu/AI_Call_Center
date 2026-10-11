"""Opt-in: runs the real faster-whisper ``tiny`` model (downloads it on first use)."""

import wave
from pathlib import Path

import numpy as np
import pytest

from call_center.stages import transcription

CALL = Path(__file__).parent.parent / "fixtures" / "call_stereo.wav"
TURNS = ["agent", "customer", "agent", "customer"]


def _run(path: Path) -> dict:
    result = transcription.run({"source_file": str(path), "stages_completed": []})
    assert "status" not in result, result.get("status_reason")
    return result


def _with_crosstalk(source: Path, target: Path, bleed: float) -> Path:
    """Copy of a stereo WAV where each channel also carries ``bleed`` of the other."""
    with wave.open(str(source), "rb") as wav:
        params = wav.getparams()
        frames = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    left, right = frames[0::2].astype(np.float64), frames[1::2].astype(np.float64)
    mixed = np.empty(frames.size, dtype=np.float64)
    mixed[0::2], mixed[1::2] = left + bleed * right, right + bleed * left
    with wave.open(str(target), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(np.clip(mixed, -32768, 32767).astype(np.int16).tobytes())
    return target


@pytest.mark.slow
def test_real_tiny_model_transcribes_call(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "tiny")
    result = _run(CALL)

    segments = result["transcript"].segments
    assert segments
    text = " ".join(s.text for s in segments).lower()
    assert "thank" in text
    assert "calling" in text
    assert [s.speaker for s in segments] == TURNS
    assert result["audit"][0].detail == f"{len(segments)} segments; stereo, agent=left"
    starts = [s.start for s in segments]
    assert starts == sorted(starts)
    assert all(s.end >= s.start for s in segments)


@pytest.mark.slow
def test_real_tiny_model_labels_call_with_crosstalk(monkeypatch, tmp_path):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "tiny")
    path = _with_crosstalk(CALL, tmp_path / "crosstalk.wav", 0.3)
    result = _run(path)

    assert [s.speaker for s in result["transcript"].segments] == TURNS
