"""Stub injection_detection stage."""

from call_center.models import AuditEvent
from call_center.state import PipelineState

NAME = "injection_detection"


def run(state: PipelineState) -> dict:
    # A real implementation that detects an injection returns status "blocked", a
    # status_reason, and a "blocked" AuditEvent; the graph then skips to the report stage.
    return {
        "stages_completed": [NAME],
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
