"""Epic 4.6 opt-in live check: both LLM stages on OpenAI with one redacted transcript."""

import pytest
from helpers import LIVE_REDACTED

from call_center.config import load_settings
from call_center.models import QAScores, Summary
from call_center.stages import qa_scoring, summarization

pytestmark = pytest.mark.live

BASE_STATE = {
    "source_file": "live.wav",
    "stages_completed": [],
    "redacted_transcript": LIVE_REDACTED,
}


def test_openai_live_summarization_then_qa_scoring(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    if load_settings().openai_api_key is None:
        pytest.skip("OPENAI_API_KEY is not configured")

    sum_result = summarization.run(BASE_STATE)
    assert sum_result.get("status") != "failed", sum_result.get("status_reason")
    summary = sum_result["summary"]
    assert isinstance(summary, Summary)
    assert summary.call_purpose.strip()

    score_result = qa_scoring.run({**BASE_STATE, **sum_result})
    assert score_result.get("status") != "failed", score_result.get("status_reason")
    scores = score_result["qa_scores"]
    assert isinstance(scores, QAScores)
    for name in ("professionalism", "empathy", "resolution", "compliance", "clarity"):
        dimension = getattr(scores, name)
        assert 1 <= dimension.score <= 10
        assert dimension.rationale.strip()
    assert 10.0 <= scores.overall <= 100.0
