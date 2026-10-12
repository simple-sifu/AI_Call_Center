"""Injection detection stage: blocks a call whose transcript addresses the AI."""

from call_center.injection import CATALOGUE, scan
from call_center.models import AuditEvent
from call_center.state import PipelineState

NAME = "injection_detection"


def run(state: PipelineState) -> dict:
    transcript = state.get("transcript")
    segments = transcript.segments if transcript else ()
    # Joined with a space so a phrase split across segments is still caught.
    matches = scan(" ".join(s.text for s in segments))
    if not matches:
        return {
            "stages_completed": [NAME],
            "audit": [
                AuditEvent(
                    stage=NAME,
                    outcome="ok",
                    detail=f"no injection patterns matched ({len(CATALOGUE)} checked)",
                )
            ],
        }
    # Ids and categories only: never quote transcript text.
    reason = "prompt injection detected: " + ", ".join(f"{p.id} ({p.category})" for p in matches)
    return {
        "stages_completed": [NAME],
        "status": "blocked",
        "status_reason": reason,
        "audit": [AuditEvent(stage=NAME, outcome="blocked", detail=reason)],
    }
