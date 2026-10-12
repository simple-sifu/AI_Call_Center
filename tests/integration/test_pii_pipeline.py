import re
from pathlib import Path

import pytest
from helpers import DIGIT_WORDS, FakeTranscriber

from call_center import asr
from call_center.graph import run_pipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"
CALL_MONO = FIXTURES / "call_mono.wav"
SEEDED = {
    "123-45-6789": asr.RawSegment(0.0, 1.0, "My social is 123-45-6789."),
    "4111 1111 1111 1111": asr.RawSegment(1.0, 2.0, "The card is 4111 1111 1111 1111."),
    "jane.doe@example.com": asr.RawSegment(2.0, 3.0, "Email jane.doe@example.com please."),
    "(555) 123-4567": asr.RawSegment(3.0, 4.0, "Call me on (555) 123-4567 tonight."),
}


def test_seeded_values_never_reach_redacted_transcript_or_audit(monkeypatch, llm_guard):
    monkeypatch.setattr(asr, "get_transcriber", lambda model_size: FakeTranscriber(SEEDED.values()))
    state = run_pipeline(str(CALL_MONO))
    llm_guard.assert_redacted_only("4111111111111111")

    assert state["status"] == "completed", state["status_reason"]
    redacted = state["redacted_transcript"].model_dump_json()
    audit = " ".join(e.model_dump_json() for e in state["audit"])
    for value in SEEDED:
        assert value not in redacted
        assert value not in audit
    assert [s.text for s in state["redacted_transcript"].segments] == [
        "My social is [SSN].",
        "The card is [CARD].",
        "Email [EMAIL] please.",
        "Call me on [PHONE] tonight.",
    ]
    [event] = [e for e in state["audit"] if e.stage == "pii_redaction"]
    assert (event.outcome, event.detail) == ("ok", "redacted SSN 1, CARD 1, EMAIL 1, PHONE 1")


SPOKEN = [
    asr.RawSegment(0.0, 1.0, "The card is four one one one, one one one one, one one one one,"),
    asr.RawSegment(1.0, 2.0, "one one one one. My social is one two three, four five,"),
    asr.RawSegment(2.0, 3.0, "six seven eight nine. Call eight five five oh one nine nine."),
    asr.RawSegment(3.0, 4.0, "Thanks. One moment, I have two options."),
]


def test_spoken_values_never_reach_redacted_transcript(monkeypatch, llm_guard):
    monkeypatch.setattr(asr, "get_transcriber", lambda model_size: FakeTranscriber(SPOKEN))
    state = run_pipeline(str(CALL_MONO))
    llm_guard.assert_redacted_only("4111111111111111")

    assert state["status"] == "completed", state["status_reason"]
    texts = [s.text for s in state["redacted_transcript"].segments]
    assert texts == [
        "The card is [CARD]",
        ". My social is [SSN]",
        ". Call [PHONE].",
        "Thanks. One moment, I have two options.",
    ]
    for text in texts[:3]:
        assert not DIGIT_WORDS & set(re.split(r"[^a-z]+", text.casefold())), text
    [event] = [e for e in state["audit"] if e.stage == "pii_redaction"]
    assert (event.outcome, event.detail) == ("ok", "redacted SSN 1, CARD 1, EMAIL 0, PHONE 1")


@pytest.mark.slow
@pytest.mark.parametrize("name", ["call_stereo.wav", "call_mono.wav"])
def test_real_fixture_calls_redact_to_same_text(monkeypatch, llm_guard, name):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "tiny")
    state = run_pipeline(str(FIXTURES / name))
    llm_guard.assert_redacted_only()

    assert state["status"] == "completed", state["status_reason"]
    assert state["transcript"].segments
    assert state["redacted_transcript"] == state["transcript"]
