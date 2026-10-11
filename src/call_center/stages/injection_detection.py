"""Stub injection_detection stage."""

from call_center.state import PipelineState

NAME = "injection_detection"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
