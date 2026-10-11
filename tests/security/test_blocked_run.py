"""Guard: a blocked run never reaches PII redaction or the LLM stages, and LLM stages
read only the redacted transcript."""

import wave

import pytest

from call_center.graph import run_pipeline
from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.stages import injection_detection, pii_redaction, qa_scoring, summarization


def test_blocked_at_injection_skips_to_report(monkeypatch, tmp_path):
    def blocked(state):
        return {
            "stages_completed": [injection_detection.NAME],
            "status": "blocked",
            "status_reason": "prompt injection detected",
            "audit": [AuditEvent(stage=injection_detection.NAME, outcome="blocked")],
        }

    monkeypatch.setattr(injection_detection, "run", blocked)
    # Transcription reads the file's audio stream for speaker labelling, so it must be a
    # real (silent) WAV; the fake ASR ignores the content.
    call = tmp_path / "call.wav"
    with wave.open(str(call), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\0\0" * 1_600)
    state = run_pipeline(str(call))

    assert state["stages_completed"] == [
        "intake",
        "transcription",
        "injection_detection",
        "report",
    ]
    assert state["status"] == "blocked"
    assert state["status_reason"] == "prompt injection detected"
    assert state["redacted_transcript"] is None
    assert state["summary"] is None
    assert state["qa_scores"] is None
    assert [(e.stage, e.outcome) for e in state["audit"][-2:]] == [
        ("injection_detection", "blocked"),
        ("report", "ok"),
    ]


class _NoRawTranscript(dict):
    """State mapping that fails any read of the raw transcript."""

    def __getitem__(self, key):
        if key == "transcript":
            raise AssertionError("LLM stage read the raw transcript")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == "transcript":
            raise AssertionError("LLM stage read the raw transcript")
        return super().get(key, default)


@pytest.mark.parametrize("stage", [summarization, qa_scoring], ids=lambda m: m.NAME)
def test_llm_stages_never_read_raw_transcript(stage):
    redacted = Transcript(
        segments=[TranscriptSegment(speaker="agent", start=0, end=1, text="[REDACTED]")],
        audio_sha256="0" * 64,
    )
    state = _NoRawTranscript(
        source_file="x.wav",
        stages_completed=[],
        transcript=redacted,
        redacted_transcript=redacted,
        status="running",
    )
    result = stage.run(state)
    assert stage.NAME in result["stages_completed"]


def test_pii_redaction_masks_text_and_keeps_timing():
    source = Transcript(
        segments=[TranscriptSegment(speaker="customer", start=1, end=2, text="SSN 123")],
        audio_sha256="a" * 64,
    )
    redacted = pii_redaction.run({"transcript": source})["redacted_transcript"]
    assert redacted.audio_sha256 == source.audio_sha256
    assert [(s.speaker, s.start, s.end, s.text) for s in redacted.segments] == [
        ("customer", 1, 2, "[REDACTED]")
    ]
    assert pii_redaction.run({})["redacted_transcript"].segments == ()
