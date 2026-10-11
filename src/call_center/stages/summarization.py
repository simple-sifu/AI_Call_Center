"""Stub summarization stage."""

from call_center.state import PipelineState

NAME = "summarization"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
