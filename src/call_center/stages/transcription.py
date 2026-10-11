"""Transcription stage: audio file to a ``Transcript`` via the configured ASR model.

The mix is transcribed once. For stereo audio each segment is then labelled ``agent`` or
``customer`` by the louder channel in its window; any other channel count is labelled
``speaker_1`` throughout, and the audit detail says no separation was possible.

Raw ASR segments are cached by audio SHA-256 and model size (``transcript_cache``), so
identical audio skips the model. Labelling always re-runs, so a changed
``AGENT_CHANNEL`` never yields stale labels. The audit detail ends with
``cache hit``, ``cache miss`` or ``cache off``.
"""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from call_center import asr, speakers, transcript_cache
from call_center.config import Settings, format_config_error, load_settings
from call_center.models import AuditEvent, Transcript, TranscriptSegment
from call_center.state import PipelineState

NAME = "transcription"


def _segment(raw: asr.RawSegment, speaker: str) -> TranscriptSegment:
    start = max(0.0, float(raw.start))
    end = max(start, float(raw.end))
    return TranscriptSegment(speaker=speaker, start=start, end=end, text=raw.text)


def _separation(channel_count: int, separated: bool, agent_channel: str) -> str:
    if channel_count == 2:
        if not separated:
            return "dual-mono: no speaker separation"
        return f"stereo, agent={agent_channel}"
    if channel_count == 1:
        return "mono: no speaker separation"
    return f"{channel_count} channels: no speaker separation"


def _failed(reason: str) -> dict:
    return {
        "stages_completed": [NAME],
        "status": "failed",
        "status_reason": reason,
        "audit": [AuditEvent(stage=NAME, outcome="failed", detail=reason)],
    }


def _raw_segments(path: Path, digest: str, settings: Settings) -> tuple[list[asr.RawSegment], str]:
    """Raw segments from the cache or the transcriber, and the cache note for the audit."""
    size = settings.whisper_model_size
    if settings.transcript_cache == "off":
        return list(asr.get_transcriber(size).transcribe(path)), "cache off"
    cache_dir = settings.transcript_cache_dir
    cached = transcript_cache.load(cache_dir, digest, size)
    if cached is not None:
        return cached, "cache hit"
    raw_segments = list(asr.get_transcriber(size).transcribe(path))
    if not transcript_cache.store(cache_dir, digest, size, raw_segments):
        return raw_segments, "cache miss; cache write failed"
    return raw_segments, "cache miss"


def run(state: PipelineState) -> dict:
    path = Path(state["source_file"])
    try:
        settings = load_settings()
    except ValidationError as error:
        return _failed("invalid configuration: " + format_config_error(error))
    try:
        with path.open("rb") as audio:
            digest = hashlib.file_digest(audio, "sha256").hexdigest()
        raw_segments, cache_note = _raw_segments(path, digest, settings)
        channels, rate, channel_count = asr.load_channels(path)
        labels = speakers.label_segments(raw_segments, channels, rate, settings.agent_channel)
        segments = tuple(
            _segment(raw, label) for raw, label in zip(raw_segments, labels, strict=True)
        )
        transcript = Transcript(segments=segments, audio_sha256=digest)
    except Exception as error:  # any failure halts the run; none escapes the graph
        return _failed(f"transcription failed: {type(error).__name__}: {error}")
    separation = _separation(channel_count, bool(channels), settings.agent_channel)
    detail = f"{len(segments)} segments; {separation}; {cache_note}"
    return {
        "stages_completed": [NAME],
        "transcript": transcript,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail=detail)],
    }
