"""Stub qa_scoring stage. LLM-backed: reads only the redacted transcript."""

from call_center.models import AuditEvent, DimensionScore, QAScores
from call_center.state import PipelineState

NAME = "qa_scoring"

_STUB = DimensionScore(score=5, rationale="placeholder")
_PLACEHOLDER = QAScores(
    professionalism=_STUB,
    empathy=_STUB,
    resolution=_STUB,
    compliance=_STUB,
    clarity=_STUB,
)


def run(state: PipelineState) -> dict:
    return {
        "stages_completed": [NAME],
        "qa_scores": _PLACEHOLDER,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
