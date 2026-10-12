"""Opt-in live check: one real OpenAI QA scoring call (``uv run pytest -m live``).

Reads the real key from the shell or ``.env``; skips when none is configured. Uses the
fixed redacted transcript of the summarization live check.
"""

import pytest
from helpers import LIVE_REDACTED

from call_center.config import load_settings
from call_center.models import QAScores
from call_center.stages import qa_scoring

pytestmark = pytest.mark.live


def test_openai_returns_valid_qa_scores(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    if load_settings().openai_api_key is None:
        pytest.skip("OPENAI_API_KEY is not configured")
    result = qa_scoring.run(
        {"source_file": "live.wav", "stages_completed": [], "redacted_transcript": LIVE_REDACTED}
    )
    assert result.get("status") != "failed", result.get("status_reason")
    scores = result["qa_scores"]
    assert isinstance(scores, QAScores)
    for name in ("professionalism", "empathy", "resolution", "compliance", "clarity"):
        dimension = getattr(scores, name)
        assert 1 <= dimension.score <= 10
        assert dimension.rationale.strip()
    assert 10.0 <= scores.overall <= 100.0
    [event] = result["audit"]
    assert event.outcome == "ok"
    assert event.detail.startswith("scored with openai ")
    assert f"overall {scores.overall}" in event.detail
