"""End to end: real audio through the real ASR and graph, with the LLM-stage guard.

The slow tests run the committed two-voice calls (``tests/fixtures/make_call.py``) through
the tiny model. The fast tests prove the guard itself catches a leaky stage.
"""

import re
from pathlib import Path

import pytest
from security.llm_guard import LLMGuard, card_digit_leaks

from call_center import asr
from call_center.graph import run_pipeline
from call_center.models import AuditEvent
from call_center.stages import pii_redaction, summarization

FIXTURES = Path(__file__).parent.parent / "fixtures"
CALL_INJECTION = FIXTURES / "call_injection.wav"
CALL_CARD = FIXTURES / "call_card.wav"
CALL_MONO = FIXTURES / "call_mono.wav"
CALL_DICTATION = FIXTURES / "call_dictation.wav"
SSN = "123456789"
CARD = "4539148803436467"
CARD_GROUPS = ("4539", "1488", "0343", "6467")
BLOCKED_STAGES = ["intake", "transcription", "injection_detection", "report"]


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _text(transcript) -> str:
    return " ".join(segment.text for segment in transcript.segments)


@pytest.fixture
def tiny(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "tiny")


@pytest.mark.slow
def test_injection_call_is_blocked_before_any_llm_stage(tiny, llm_guard):
    state = run_pipeline(str(CALL_INJECTION))

    assert state["status"] == "blocked", _text(state["transcript"])
    assert "INJ-01" in state["status_reason"]
    assert state["stages_completed"] == BLOCKED_STAGES
    assert state["redacted_transcript"] is None
    assert state["summary"] is None
    assert state["qa_scores"] is None
    llm_guard.assert_not_run()


@pytest.mark.slow
def test_card_call_reaches_llm_stages_redacted(tiny, llm_guard):
    state = run_pipeline(str(CALL_CARD))

    assert state["status"] == "completed", state["status_reason"]
    # The ASR heard the card, so the redaction below is tested on it.
    assert CARD in _digits(_text(state["transcript"])), _text(state["transcript"])
    redacted = _text(state["redacted_transcript"])
    assert "[CARD]" in redacted
    for group in CARD_GROUPS:
        assert group not in redacted
    assert not card_digit_leaks(redacted, CARD), redacted
    [event] = [e for e in state["audit"] if e.stage == "pii_redaction"]
    assert (event.outcome, event.detail) == ("ok", "redacted SSN 0, CARD 1, EMAIL 0, PHONE 0")
    audit = " ".join(e.model_dump_json() for e in state["audit"])
    assert not card_digit_leaks(audit, CARD)
    llm_guard.assert_redacted_only(CARD)


@pytest.mark.slow
def test_dictation_call_reaches_llm_stages_without_card_digits(tiny, llm_guard):
    state = run_pipeline(str(CALL_DICTATION))

    assert state["status"] == "completed", state["status_reason"]
    raw = _text(state["transcript"])
    assert CARD in _digits(raw), raw
    redacted = _text(state["redacted_transcript"])
    assert "[CARD]" in redacted
    assert not card_digit_leaks(redacted, CARD), redacted
    audit = " ".join(e.model_dump_json() for e in state["audit"])
    assert not card_digit_leaks(audit, CARD)
    llm_guard.assert_redacted_only(CARD)


@pytest.mark.slow
def test_dictation_call_reaches_llm_stages_without_ssn_digits(tiny, llm_guard):
    # The tiny model writes the SSN as hyphen fragments across segments ("1-2-3" +
    # "4-5-6-7-8-9"), which only the dictated pass redacts.
    state = run_pipeline(str(CALL_DICTATION))

    assert state["status"] == "completed", state["status_reason"]
    raw = _text(state["transcript"])
    assert SSN in _digits(raw), raw
    redacted = _text(state["redacted_transcript"])
    assert "[SSN]" in redacted and "[CARD]" in redacted, redacted
    # No stretch of 3 or more digits in order, as digits or number words, of the SSN or
    # of any card group survives (a partial leak such as "1-2-3 [SSN]" fails here).
    for value in (SSN, *CARD_GROUPS):
        assert not card_digit_leaks(redacted, value, run=3), (value, redacted)
    [event] = [e for e in state["audit"] if e.stage == "pii_redaction"]
    assert (event.outcome, event.detail) == ("ok", "redacted SSN 1, CARD 1, EMAIL 0, PHONE 0")
    llm_guard.assert_redacted_only(CARD, SSN)


@pytest.mark.slow
def test_card_call_fails_the_guard_when_a_stage_reads_the_raw_transcript(tiny, monkeypatch):
    real = summarization.run

    def leaky(state):
        state["transcript"]
        return real(state)

    monkeypatch.setattr(summarization, "run", leaky)
    guard = LLMGuard.install(monkeypatch)
    with pytest.raises(AssertionError, match="raw transcript"):
        run_pipeline(str(CALL_CARD))
    assert guard.raw_reads == [("summarization", "[]")]


@pytest.mark.slow
@pytest.mark.parametrize("name", ["call_stereo.wav", "call_mono.wav"])
def test_existing_fixture_calls_pass_the_guard(tiny, llm_guard, name):
    state = run_pipeline(str(FIXTURES / name))

    assert state["status"] == "completed", state["status_reason"]
    llm_guard.assert_redacted_only(CARD)


# Fast: the guard on a fake ASR that reads the card out.

CARD_SEGMENTS = [
    asr.RawSegment(0.0, 1.0, "What is the card number?"),
    asr.RawSegment(1.0, 2.0, "It's 4539-1488-0343-6467."),
]


class _Fake:
    def transcribe(self, path):
        return CARD_SEGMENTS


@pytest.fixture
def card_asr(monkeypatch):
    monkeypatch.setattr(asr, "get_transcriber", lambda model_size: _Fake())


def test_guard_passes_redacted_card_call(card_asr, llm_guard):
    state = run_pipeline(str(CALL_MONO))

    assert state["status"] == "completed", state["status_reason"]
    llm_guard.assert_redacted_only(CARD)


@pytest.mark.parametrize(
    "how", ["[]", "get", "items", "dict", "unpack", "copy", "repr", "str", "f-string"]
)
def test_guard_fails_a_stage_that_reads_the_raw_transcript(card_asr, monkeypatch, how):
    real = summarization.run
    reads = {
        "[]": lambda s: s["transcript"],
        "get": lambda s: s.get("transcript"),
        "items": lambda s: list(s.items()),
        "dict": lambda s: dict(s)["transcript"],
        "unpack": lambda s: {**s}["transcript"],
        "copy": lambda s: s.copy(),
        "repr": lambda s: repr(s),
        "str": lambda s: str(s),
        "f-string": lambda s: f"Summarize this call: {s}",
    }

    def leaky(state):
        # A stage that swallows the failure is still caught by the recorded read.
        try:
            reads[how](state)
        except AssertionError:
            pass
        return real(state)

    monkeypatch.setattr(summarization, "run", leaky)
    guard = LLMGuard.install(monkeypatch)
    run_pipeline(str(CALL_MONO))
    with pytest.raises(AssertionError, match="raw transcript"):
        guard.assert_redacted_only(CARD)


def test_guard_fails_unredacted_text(card_asr, monkeypatch):
    def passthrough(state):
        return {
            "stages_completed": [pii_redaction.NAME],
            "redacted_transcript": state["transcript"],
            "audit": [AuditEvent(stage=pii_redaction.NAME, outcome="ok")],
        }

    monkeypatch.setattr(pii_redaction, "run", passthrough)
    guard = LLMGuard.install(monkeypatch)
    run_pipeline(str(CALL_MONO))
    with pytest.raises(AssertionError, match="card digits"):
        guard.assert_redacted_only(CARD)


def test_guard_fails_when_a_stage_runs_for_a_blocked_call(card_asr, llm_guard):
    run_pipeline(str(CALL_MONO))
    with pytest.raises(AssertionError, match="blocked call"):
        llm_guard.assert_not_run()


@pytest.mark.parametrize(
    ("text", "piece"),
    [
        ("It's [CARD].", None),
        ("It's 4539-1488-0343-6467.", "0343"),
        ("It's 4.539, 1.488", "9148"),
        ("four five three nine", "4539"),
        ("forty five thirty nine fourteen eighty eight", "1488"),
        ("forty five thirty nine", "4539"),
        ("fourteen eighty eight", "1488"),
        ("oh three forty three", "0343"),
        ("sixty four sixty-seven", "6467"),
        ("four five three nine one four double eight", "1488"),
        ("double four eight eight", None),
        ("one four double eight", "1488"),
        ("triple four", None),
        ("call 4 5 at 3 9", None),
        ("the code is 1234", None),
    ],
)
def test_card_digit_leaks(text, piece):
    found = card_digit_leaks(text, CARD)
    assert piece in found if piece else found == [], found
