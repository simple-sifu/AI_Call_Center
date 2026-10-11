"""Stub report stage."""

from call_center.state import PipelineState

NAME = "report"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
