"""Stub summarization stage. LLM-backed: reads only the redacted transcript."""

from call_center.models import AuditEvent, SentimentTrajectory, Summary
from call_center.state import PipelineState

NAME = "summarization"

_PLACEHOLDER = Summary(
    call_purpose="placeholder",
    action_items=[],
    sentiment_trajectory=SentimentTrajectory(
        opening="neutral", middle="neutral", closing="neutral"
    ),
    entities=[],
)


def run(state: PipelineState) -> dict:
    return {
        "stages_completed": [NAME],
        "summary": _PLACEHOLDER,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
