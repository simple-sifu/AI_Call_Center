from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from call_center.models import (
    QA_WEIGHTS,
    AuditEvent,
    DimensionScore,
    QAScores,
    Summary,
    Transcript,
    TranscriptSegment,
)

DIMENSIONS = ("professionalism", "empathy", "resolution", "compliance", "clarity")


def _scores(**scores: int) -> dict:
    return {dim: {"score": scores.get(dim, 5), "rationale": "r"} for dim in DIMENSIONS}


def test_segment_end_before_start_rejected():
    with pytest.raises(ValidationError):
        TranscriptSegment(speaker="agent", start=5, end=2, text="hi")


@pytest.mark.parametrize("bound", ["start", "end"])
@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_segment_rejects_inf_and_nan(bound, value):
    times = {"start": 0.0, "end": 1.0, bound: value}
    with pytest.raises(ValidationError):
        TranscriptSegment(speaker="agent", text="hi", **times)


@pytest.mark.parametrize("score", [0, 11, True, "7", 5.0])
def test_dimension_score_out_of_range_rejected(score):
    with pytest.raises(ValidationError):
        DimensionScore(score=score, rationale="r")


def test_supplied_overall_is_ignored():
    scores = QAScores.model_validate({**_scores(), "overall": 99})
    assert scores.overall == 50.0
    assert scores.model_dump()["overall"] == 50.0


def test_weights_cover_dimensions_and_sum_to_one():
    assert set(QA_WEIGHTS) == set(DIMENSIONS)
    assert sum(QA_WEIGHTS.values()) == pytest.approx(1.0)


def test_overall_is_weighted_and_deterministic():
    data = _scores(professionalism=10, empathy=8, resolution=6, compliance=4, clarity=2)
    expected = round((0.15 * 10 + 0.20 * 8 + 0.30 * 6 + 0.20 * 4 + 0.15 * 2) * 10, 1)
    first, second = QAScores.model_validate(data), QAScores.model_validate(data)
    assert first.overall == second.overall == expected == 60.0


def test_overall_bounds():
    assert QAScores.model_validate(_scores(**dict.fromkeys(DIMENSIONS, 1))).overall == 10.0
    assert QAScores.model_validate(_scores(**dict.fromkeys(DIMENSIONS, 10))).overall == 100.0


def test_models_are_frozen_and_strict():
    seg = TranscriptSegment(speaker="agent", start=0, end=1, text="hi")
    with pytest.raises(ValidationError):
        seg.text = "changed"
    with pytest.raises(ValidationError):
        TranscriptSegment(speaker="agent", start=0, end=1, text="hi", extra=1)


def test_sequences_are_immutable_tuples():
    t = Transcript(
        segments=[TranscriptSegment(speaker="agent", start=0, end=1, text="hi")],
        audio_sha256="0" * 64,
    )
    assert isinstance(t.segments, tuple)
    s = Summary.model_validate(
        {
            "call_purpose": "p",
            "action_items": ["a"],
            "entities": [{"text": "Acme", "type": "org"}],
            "sentiment_trajectory": {
                "opening": "neutral",
                "middle": "neutral",
                "closing": "neutral",
            },
        }
    )
    assert s.action_items == ("a",)
    assert isinstance(s.entities, tuple)


def test_sentiment_trajectory_requires_three_labeled_phases():
    base = {"call_purpose": "p", "action_items": [], "entities": []}
    ok = {"opening": "negative", "middle": "neutral", "closing": "positive"}
    Summary.model_validate({**base, "sentiment_trajectory": ok})
    with pytest.raises(ValidationError):
        Summary.model_validate({**base, "sentiment_trajectory": {**ok, "closing": "angry"}})
    with pytest.raises(ValidationError):
        Summary.model_validate(
            {**base, "sentiment_trajectory": {"opening": "neutral", "closing": "neutral"}}
        )


def test_audit_event_time_is_utc():
    assert AuditEvent(stage="s", outcome="ok").at.tzinfo == UTC
    local = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=5)))
    assert AuditEvent(stage="s", outcome="ok", at=local).at == local
    assert AuditEvent(stage="s", outcome="ok", at=local).at.utcoffset() == timedelta(0)
    with pytest.raises(ValidationError):
        AuditEvent(stage="s", outcome="ok", at=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        AuditEvent(stage="s", outcome="maybe")
