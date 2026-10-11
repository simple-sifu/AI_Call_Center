"""Stub pii_redaction stage."""

from call_center.state import PipelineState

NAME = "pii_redaction"


def run(state: PipelineState) -> dict:
    return {"stages_completed": [NAME]}
