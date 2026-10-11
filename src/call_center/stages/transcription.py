"""Stub transcription stage."""

from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.state import PipelineState

NAME = "transcription"

_PLACEHOLDER = Transcript(
    segments=[
        TranscriptSegment(speaker="agent", start=0.0, end=1.0, text="placeholder"),
    ],
    audio_sha256="0" * 64,
)


def run(state: PipelineState) -> dict:
    return {
        "stages_completed": [NAME],
        "transcript": _PLACEHOLDER,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
