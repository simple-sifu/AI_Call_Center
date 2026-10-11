"""Stub report stage. Always runs, including for blocked or failed runs."""

from call_center.models import AuditEvent
from call_center.state import PipelineState

NAME = "report"


def run(state: PipelineState) -> dict:
    update: dict = {
        "stages_completed": [NAME],
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
    if state.get("status", "running") == "running":
        update["status"] = "completed"
    return update
