"""Transcription stage: audio file to a ``Transcript`` via the configured ASR model.

Every segment is labelled ``speaker_1`` until speaker attribution lands (story 2.3).
"""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from call_center import asr
from call_center.config import format_config_error, load_settings
from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.state import PipelineState

NAME = "transcription"
SPEAKER = "speaker_1"


def _segment(raw: asr.RawSegment) -> TranscriptSegment:
    start = max(0.0, float(raw.start))
    end = max(start, float(raw.end))
    return TranscriptSegment(speaker=SPEAKER, start=start, end=end, text=raw.text)


def _failed(reason: str) -> dict:
    return {
        "stages_completed": [NAME],
        "status": "failed",
        "status_reason": reason,
        "audit": [AuditEvent(stage=NAME, outcome="failed", detail=reason)],
    }


def run(state: PipelineState) -> dict:
    path = Path(state["source_file"])
    try:
        model_size = load_settings().whisper_model_size
    except ValidationError as error:
        return _failed("invalid configuration: " + format_config_error(error))
    try:
        with path.open("rb") as audio:
            digest = hashlib.file_digest(audio, "sha256").hexdigest()
        transcriber = asr.get_transcriber(model_size)
        segments = tuple(_segment(raw) for raw in transcriber.transcribe(path))
        transcript = Transcript(segments=segments, audio_sha256=digest)
    except Exception as error:  # any failure halts the run; none escapes the graph
        return _failed(f"transcription failed: {type(error).__name__}: {error}")
    return {
        "stages_completed": [NAME],
        "transcript": transcript,
        "audit": [
            AuditEvent(stage=NAME, outcome="ok", detail=f"{len(segments)} segments"),
        ],
    }
