"""Stub qa_scoring stage."""

from call_center.state import PipelineState

NAME = "qa_scoring"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
