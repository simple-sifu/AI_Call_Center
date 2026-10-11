"""Stub intake stage."""

from call_center.models import AuditEvent
from call_center.state import PipelineState

NAME = "intake"


def run(state: PipelineState) -> dict:
    return {
        "stages_completed": [NAME],
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
