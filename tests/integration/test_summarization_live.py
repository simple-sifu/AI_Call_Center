"""Opt-in live check: one real OpenAI summarization call (``uv run pytest -m live``).

Reads the real key from the shell or ``.env``; skips when none is configured.
"""

import pytest

from call_center.config import load_settings
from call_center.models import Summary, Transcript, TranscriptSegment
from call_center.stages import summarization

pytestmark = pytest.mark.live

REDACTED = Transcript(
    segments=[
        TranscriptSegment(
            speaker="agent", start=0, end=3, text="Thanks for calling, how can I help?"
        ),
        TranscriptSegment(
            speaker="customer",
            start=3,
            end=9,
            text="My payment with card [CARD] was declined and I need my order shipped today.",
        ),
        TranscriptSegment(
            speaker="agent",
            start=9,
            end=14,
            text="I see the decline. I'll send you a new payment link by email right now.",
        ),
        TranscriptSegment(speaker="customer", start=14, end=16, text="Great, thank you so much."),
    ],
    audio_sha256="0" * 64,
)


def test_openai_returns_a_valid_summary(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    if load_settings().openai_api_key is None:
        pytest.skip("OPENAI_API_KEY is not configured")
    result = summarization.run(
        {"source_file": "live.wav", "stages_completed": [], "redacted_transcript": REDACTED}
    )
    assert result.get("status") != "failed", result.get("status_reason")
    assert isinstance(result["summary"], Summary)
    assert result["summary"].call_purpose
    [event] = result["audit"]
    assert event.outcome == "ok"
    assert event.detail.startswith("summarized with openai ")
