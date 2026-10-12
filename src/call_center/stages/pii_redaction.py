"""PII redaction stage: masks SSNs, card numbers, emails and phone numbers in the transcript."""

from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.pii import TYPES, redact_segments
from call_center.state import PipelineState

NAME = "pii_redaction"

_PLACEHOLDER = Transcript(segments=(), audio_sha256="0" * 64)


def run(state: PipelineState) -> dict:
    source = state.get("transcript") or _PLACEHOLDER
    # Joined with a space (inside redact_segments) so a value split across segments is
    # still caught.
    texts, counts = redact_segments([s.text for s in source.segments])
    redacted = Transcript(
        segments=tuple(
            TranscriptSegment(speaker=s.speaker, start=s.start, end=s.end, text=text)
            for s, text in zip(source.segments, texts, strict=True)
        ),
        audio_sha256=source.audio_sha256,
    )
    # Counts by type only: never quote a redacted value.
    detail = "redacted " + ", ".join(f"{kind} {counts[kind]}" for kind in TYPES)
    return {
        "stages_completed": [NAME],
        "redacted_transcript": redacted,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail=detail)],
    }
