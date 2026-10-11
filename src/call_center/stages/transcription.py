"""Stub transcription stage."""

from call_center.state import PipelineState

NAME = "transcription"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
