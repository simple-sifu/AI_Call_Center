import array
import hashlib
import math
import wave
from pathlib import Path

import pytest

from call_center import asr
from call_center.graph import run_pipeline
from call_center.models import Transcript
from call_center.stages import transcription

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE = FIXTURES / "sample.wav"
CALL_MONO = FIXTURES / "call_mono.wav"
RATE = 16_000
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
    assert [(e.stage, e.outcome, e.detail) for e in result["audit"]] == [
        ("transcription", "ok", "2 segments; mono: no speaker separation")
    ]
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


TWO_TURNS = [
    asr.RawSegment(0.0, 1.0, "Thank you for calling."),
    asr.RawSegment(1.0, 2.0, "Hi, my internet is down."),
]


def _write_wav(path: Path, channels: list[list[int]]) -> Path:
    frames = array.array("h", [sample for frame in zip(*channels, strict=True) for sample in frame])
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(len(channels))
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(frames.tobytes())
    return path


def _two_turn_channels(count: int = 2) -> list[list[int]]:
    """Channel 0 speaks in the first second, channel 1 in the second."""
    tone = [int(8000 * math.sin(2 * math.pi * 440 * n / RATE)) for n in range(RATE)]
    silence = [0] * RATE
    channels = [tone + silence, silence + tone]
    return channels + [silence + silence] * (count - 2)


def _speakers(result) -> list[str]:
    return [s.speaker for s in result["transcript"].segments]


def test_mono_call_is_one_speaker_with_audit_note(use_fake):
    fake = _Fake(TWO_TURNS)
    use_fake(fake)
    result = transcription.run(_state(CALL_MONO))

    assert "status" not in result
    assert _speakers(result) == ["speaker_1", "speaker_1"]
    assert [(e.outcome, e.detail) for e in result["audit"]] == [
        ("ok", "2 segments; mono: no speaker separation")
    ]
    assert "mono: no speaker separation" in result["audit"][0].detail
    assert fake.paths == [CALL_MONO]


@pytest.mark.parametrize(
    ("agent_channel", "expected"),
    [
        (None, ["agent", "customer"]),
        ("left", ["agent", "customer"]),
        ("right", ["customer", "agent"]),
    ],
)
def test_stereo_call_labels_by_louder_channel(
    use_fake, monkeypatch, tmp_path, agent_channel, expected
):
    if agent_channel:
        monkeypatch.setenv("AGENT_CHANNEL", agent_channel)
    path = _write_wav(tmp_path / "stereo.wav", _two_turn_channels())
    fake = _Fake(TWO_TURNS)
    use_fake(fake)
    result = transcription.run(_state(path))

    assert "status" not in result, result.get("status_reason")
    assert _speakers(result) == expected
    assert [s.text for s in result["transcript"].segments] == [s.text for s in TWO_TURNS]
    assert [e.detail for e in result["audit"]] == [
        f"2 segments; stereo, agent={agent_channel or 'left'}"
    ]
    assert fake.paths == [path]  # one transcription pass over the mix


def test_dual_mono_stereo_is_one_speaker(use_fake, tmp_path):
    mix = [a + b for a, b in zip(*_two_turn_channels(), strict=True)]
    path = _write_wav(tmp_path / "dual_mono.wav", [mix, list(mix)])
    fake = _Fake(TWO_TURNS)
    use_fake(fake)
    result = transcription.run(_state(path))

    assert "status" not in result, result.get("status_reason")
    assert _speakers(result) == ["speaker_1", "speaker_1"]
    assert [e.detail for e in result["audit"]] == ["2 segments; dual-mono: no speaker separation"]
    assert fake.paths == [path]


def test_more_than_two_channels_is_one_speaker(use_fake, tmp_path):
    path = _write_wav(tmp_path / "quad.wav", _two_turn_channels(4))
    use_fake(_Fake(TWO_TURNS))
    result = transcription.run(_state(path))

    assert "status" not in result, result.get("status_reason")
    assert _speakers(result) == ["speaker_1", "speaker_1"]
    assert [e.detail for e in result["audit"]] == ["2 segments; 4 channels: no speaker separation"]


def test_invalid_agent_channel_fails_with_safe_config_reason(use_fake, monkeypatch):
    monkeypatch.setenv("AGENT_CHANNEL", "middle")
    sizes = use_fake(_Fake(TWO_TURNS))
    state = run_pipeline(str(CALL_MONO))

    assert state["status"] == "failed"
    reason = state["status_reason"]
    assert reason.startswith("invalid configuration: ")
    assert "AGENT_CHANNEL" in reason
    assert "middle" not in reason
    assert state["transcript"] is None
    assert [(e.stage, e.outcome) for e in state["audit"]] == [
        ("intake", "ok"),
        ("transcription", "failed"),
        ("report", "ok"),
    ]
    assert sizes == []


def test_near_identical_channels_count_as_dual_mono(use_fake, tmp_path):
    import wave

    import numpy as np

    rate = 16_000
    tone = (0.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 32767).astype(np.int16)
    noise = np.random.default_rng(0).integers(-5, 6, size=rate).astype(np.int16)  # codec-level
    path = tmp_path / "dual_mono_noisy.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.column_stack([tone, tone + noise]).tobytes())
    use_fake(_Fake([asr.RawSegment(0.0, 0.5, "a"), asr.RawSegment(0.5, 1.0, "b")]))
    result = transcription.run(_state(path))
    assert [s.speaker for s in result["transcript"].segments] == ["speaker_1", "speaker_1"]
    assert "dual-mono: no speaker separation" in result["audit"][0].detail
