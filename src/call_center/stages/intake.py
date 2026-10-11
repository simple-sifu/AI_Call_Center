"""Intake stage: reject files that are too large, not audio, unreadable, or too long.

Checks run cheapest first: the size from ``stat`` (nothing is read), then the format from
the first 12 bytes (the extension is never consulted), then PyAV opens the file to
confirm an audio stream and measure its duration. A rejection sets status ``failed`` with
``status_reason`` ``rejected: <why>``, and the graph skips to the report stage.
"""

from pathlib import Path

from call_center.models import AuditEvent
from call_center.state import PipelineState

NAME = "intake"

MAX_BYTES = 50 * 1024 * 1024  # 52,428,800
MAX_SECONDS = 60 * 60
HEADER_BYTES = 12


def detect_format(header: bytes) -> str | None:
    """The audio format named by a file's first bytes, or ``None`` if none matches."""
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header[:4] == b"fLaC":
        return "flac"
    if header[:4] == b"OggS":
        return "ogg"
    if header[:3] == b"ID3":
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0:
        return "mp3"  # MPEG audio frame sync, no ID3 tag
    if header[4:8] == b"ftyp":
        return "m4a"
    return None


def _duration(path: Path) -> float | str:
    """Seconds of audio, or the reason the file cannot be read as audio."""
    import av

    try:
        # Same leniency as faster-whisper's own decode (see asr.load_channels).
        with av.open(str(path), metadata_errors="ignore") as container:
            if not container.streams.audio:
                return "no audio stream"
            if container.duration:
                return container.duration / av.time_base
            # No container duration: sum the audio packet durations (demux, no decode).
            stream = container.streams.audio[0]
            total = 0.0
            for packet in container.demux(stream):
                if packet.duration and packet.time_base:
                    total += float(packet.duration * packet.time_base)
    except Exception as error:  # any PyAV failure means the audio is unreadable
        return getattr(error, "strerror", None) or f"{type(error).__name__}: {error}"
    return total if total > 0 else "duration unknown"


def check(path: str | Path) -> tuple[str, float, int] | str:
    """``(format, seconds, size)`` for an accepted file, or the reason it is rejected."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as error:
        return f"unreadable file: {error.strerror or error}"
    if size > MAX_BYTES:
        return f"file too large: {size:,} bytes (limit {MAX_BYTES:,} bytes)"
    try:
        with path.open("rb") as audio:
            header = audio.read(HEADER_BYTES)
    except OSError as error:
        return f"unreadable file: {error.strerror or error}"
    fmt = detect_format(header)
    if fmt is None:
        return "unsupported format: content is not WAV, MP3, FLAC, OGG or M4A"
    seconds = _duration(path)
    if isinstance(seconds, str):
        return f"unreadable audio: {seconds}"
    if seconds > MAX_SECONDS:
        return f"too long: {seconds / 60:.1f} min ({seconds:,.1f} s), limit {MAX_SECONDS // 60} min"
    return fmt, seconds, size


def run(state: PipelineState) -> dict:
    result = check(state["source_file"])
    if isinstance(result, str):
        reason = f"rejected: {result}"
        return {
            "stages_completed": [NAME],
            "status": "failed",
            "status_reason": reason,
            "audit": [AuditEvent(stage=NAME, outcome="failed", detail=reason)],
        }
    fmt, seconds, size = result
    detail = f"{fmt}, {seconds:.1f} s, {size / 1_000_000:.1f} MB"
    return {
        "stages_completed": [NAME],
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail=detail)],
    }
