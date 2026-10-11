"""Stub intake stage."""

from call_center.state import PipelineState

NAME = "intake"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
