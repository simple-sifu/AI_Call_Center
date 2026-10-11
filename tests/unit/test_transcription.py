import hashlib
from pathlib import Path

import pytest

from call_center import asr
from call_center.graph import run_pipeline
from call_center.models import Transcript
from call_center.stages import transcription

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE = FIXTURES / "sample.wav"
# Captured at import, before the autouse fake replaces it for each test.
_REAL_GET_TRANSCRIBER = asr.get_transcriber


class _Fake:
    def __init__(self, segments=(), error=None):
        self.segments = list(segments)
        self.error = error
        self.paths = []

    def transcribe(self, path):
        self.paths.append(Path(path))
        if self.error:
            raise self.error
        return self.segments


@pytest.fixture
def use_fake(monkeypatch):
    def install(fake):
        sizes = []

        def get(model_size):
            sizes.append(model_size)
            return fake

        monkeypatch.setattr(asr, "get_transcriber", get)
        return sizes

    return install


def _state(path):
    return {"source_file": str(path), "stages_completed": []}


def test_fake_segments_map_to_speaker_1_transcript(use_fake):
    fake = _Fake(
        [
            asr.RawSegment(0.0, 1.5, "Thank you for calling."),
            asr.RawSegment(1.5, 3.25, "Hi, my internet is down."),
        ]
    )
    use_fake(fake)
    result = transcription.run(_state(SAMPLE))

    transcript = result["transcript"]
    assert isinstance(transcript, Transcript)
    assert [(s.speaker, s.start, s.end, s.text) for s in transcript.segments] == [
        ("speaker_1", 0.0, 1.5, "Thank you for calling."),
        ("speaker_1", 1.5, 3.25, "Hi, my internet is down."),
    ]
    assert transcript.audio_sha256 == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert fake.paths == [SAMPLE]
    assert result["stages_completed"] == ["transcription"]
    assert [(e.stage, e.outcome) for e in result["audit"]] == [("transcription", "ok")]
    assert "status" not in result


def test_no_speech_gives_empty_segments(use_fake):
    # A fake that hears nothing, as the real model does on the tone in sample.wav.
    use_fake(_Fake())
    result = transcription.run(_state(SAMPLE))
    assert result["transcript"].segments == ()
    assert result["transcript"].audio_sha256 == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert [(e.stage, e.outcome) for e in result["audit"]] == [("transcription", "ok")]


@pytest.mark.parametrize("size", [None, "base"])
def test_transcriber_built_with_configured_model_size(use_fake, monkeypatch, size):
    if size:
        monkeypatch.setenv("WHISPER_MODEL_SIZE", size)
    sizes = use_fake(_Fake())
    transcription.run(_state(SAMPLE))
    assert sizes == [size or "tiny"]


def test_get_transcriber_is_lazy_and_cached_per_size():
    get = _REAL_GET_TRANSCRIBER  # the real factory; building it loads no model
    get.cache_clear()
    try:
        tiny = get("tiny")
        assert isinstance(tiny, asr.FasterWhisperTranscriber)
        assert tiny._model is None
        assert get("tiny") is tiny
        assert get("base") is not tiny
        assert get("base").model_size == "base"
    finally:
        get.cache_clear()


def test_transcriber_error_fails_run_and_skips_to_report(use_fake):
    use_fake(_Fake(error=RuntimeError("decode failed")))
    state = run_pipeline(str(SAMPLE))

    assert state["status"] == "failed"
    assert "decode failed" in state["status_reason"]
    assert "RuntimeError" in state["status_reason"]
    assert state["transcript"] is None
    assert state["stages_completed"] == ["intake", "transcription", "report"]
    assert [(e.stage, e.outcome) for e in state["audit"]] == [
        ("intake", "ok"),
        ("transcription", "failed"),
        ("report", "ok"),
    ]
    assert "decode failed" in state["audit"][1].detail


def test_invalid_model_size_fails_with_safe_config_reason(use_fake, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "huge")
    sizes = use_fake(_Fake())
    result = transcription.run(_state(SAMPLE))

    assert result["status"] == "failed"
    reason = result["status_reason"]
    assert reason.startswith("invalid configuration: ")
    assert "WHISPER_MODEL_SIZE" in reason
    assert "huge" not in reason
    assert "input_value" not in reason
    assert [(e.stage, e.outcome, e.detail) for e in result["audit"]] == [
        ("transcription", "failed", reason)
    ]
    assert sizes == []
