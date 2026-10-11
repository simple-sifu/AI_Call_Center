"""Stub pii_redaction stage."""

from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.state import PipelineState

NAME = "pii_redaction"

_PLACEHOLDER = Transcript(segments=(), audio_sha256="0" * 64)


def run(state: PipelineState) -> dict:
    # Stub: redacts every segment's text wholesale. Real redaction replaces this.
    source = state.get("transcript") or _PLACEHOLDER
    redacted = Transcript(
        segments=tuple(
            TranscriptSegment(speaker=s.speaker, start=s.start, end=s.end, text="[REDACTED]")
            for s in source.segments
        ),
        audio_sha256=source.audio_sha256,
    )
    return {
        "stages_completed": [NAME],
        "redacted_transcript": redacted,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail="stub")],
    }
