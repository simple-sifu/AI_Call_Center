"""Opt-in: runs the real faster-whisper ``tiny`` model (downloads it on first use)."""

from pathlib import Path

import pytest

from call_center.stages import transcription

CALL = Path(__file__).parent.parent / "fixtures" / "call_stereo.wav"


@pytest.mark.slow
def test_real_tiny_model_transcribes_call(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "tiny")
    result = transcription.run({"source_file": str(CALL), "stages_completed": []})

    assert "status" not in result, result.get("status_reason")
    segments = result["transcript"].segments
    assert segments
    text = " ".join(s.text for s in segments).lower()
    assert "thank" in text
    assert "calling" in text
    assert all(s.speaker == "speaker_1" for s in segments)
    starts = [s.start for s in segments]
    assert starts == sorted(starts)
    assert all(s.end >= s.start for s in segments)
