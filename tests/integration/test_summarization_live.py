"""Opt-in live check: one real OpenAI summarization call (``uv run pytest -m live``).

Reads the real key from the shell or ``.env``; skips when none is configured.
"""

import pytest
from helpers import LIVE_REDACTED

from call_center.config import load_settings
from call_center.models import Summary
from call_center.stages import summarization

pytestmark = pytest.mark.live

REDACTED = LIVE_REDACTED


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
