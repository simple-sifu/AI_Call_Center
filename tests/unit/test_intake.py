import time
import wave
from pathlib import Path

import pytest

from call_center import asr
from call_center.graph import run_pipeline
from call_center.stages import intake

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"RIFF\x24\x00\x00\x00WAVE", "wav"),
        (b"fLaC\x00\x00\x00\x22\x04\x80\x04\x80", "flac"),
        (b"OggS\x00\x02\x00\x00\x00\x00\x00\x00", "ogg"),
        (b"ID3\x04\x00\x00\x00\x00\x00\x23TS", "mp3"),
        (b"\xff\xfb\x90\x64\x00\x00\x00\x00\x00\x00\x00\x00", "mp3"),  # frame sync, no ID3
        (b"\xff\xe3\x18\xc4\x00\x00\x00\x00\x00\x00\x00\x00", "mp3"),  # MPEG 2.5 sync
        (b"\x00\x00\x00\x1cftypM4A ", "m4a"),
        (b"RIFF\x24\x00\x00\x00AVI ", None),  # RIFF but not WAVE
        (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01", None),  # JPEG: 0xFF, but no frame sync
        (b"\xff\x1f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", None),  # top 3 bits not set
        (b"ftyp\x00\x00\x00\x00\x00\x00\x00\x00", None),  # ftyp at the wrong offset
        (b"just some notes", None),
        (b"", None),
        (b"\xff", None),
    ],
)
def test_detect_format(header, expected):
    assert intake.detect_format(header) == expected


@pytest.mark.parametrize("name", ["sample.wav", "tone.mp3", "tone.flac", "tone.ogg", "tone.m4a"])
def test_each_format_is_accepted(name):
    path = FIXTURES / name
    fmt, seconds, size = intake.check(path)
    assert fmt == path.suffix[1:]
    assert seconds == pytest.approx(1.0, abs=0.1)
    assert size == path.stat().st_size
    result = intake.run({"source_file": str(path), "stages_completed": []})
    assert "status" not in result
    assert result["stages_completed"] == ["intake"]
    [event] = result["audit"]
    assert event.outcome == "ok"
    assert event.detail.startswith(f"{fmt}, 1.0 s, ")
    assert event.detail.endswith(" MB")


def test_success_detail_format():
    result = intake.run({"source_file": str(FIXTURES / "call_stereo.wav")})
    assert result["audit"][0].detail == "wav, 14.4 s, 0.9 MB"


def _rejection(path: Path) -> str:
    result = intake.run({"source_file": str(path), "stages_completed": []})
    assert result["stages_completed"] == ["intake"]
    assert result["status"] == "failed"
    [event] = result["audit"]
    assert (event.stage, event.outcome) == ("intake", "failed")
    assert event.detail == result["status_reason"]
    return result["status_reason"]


def test_renamed_text_file_is_unsupported(tmp_path):
    fake = tmp_path / "fake.wav"
    fake.write_text("meeting notes: call the customer back on Tuesday\n")
    assert _rejection(fake).startswith("rejected: unsupported format")


def test_valid_magic_corrupt_body_is_unreadable(tmp_path):
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"RIFF\x00\x10\x00\x00WAVE" + bytes(range(256)) * 16)
    assert _rejection(corrupt).startswith("rejected: unreadable audio")


def test_missing_file_is_rejected(tmp_path):
    assert _rejection(tmp_path / "gone.wav").startswith("rejected: unreadable file")


def _sparse_wav(path: Path, size: int) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
    with path.open("r+b") as f:
        f.truncate(size)
    return path


def test_too_large_is_rejected_without_reading(tmp_path, monkeypatch):
    big = _sparse_wav(tmp_path / "big.wav", intake.MAX_BYTES + 1)

    def no_read(*args, **kwargs):
        raise AssertionError("an oversized file was opened")

    monkeypatch.setattr(Path, "open", no_read)
    monkeypatch.setattr("av.open", no_read)
    reason = _rejection(big)
    assert reason == "rejected: file too large: 52,428,801 bytes (limit 52,428,800 bytes)"


def test_at_size_limit_is_not_rejected_for_size(tmp_path):
    edge = _sparse_wav(tmp_path / "edge.wav", intake.MAX_BYTES)
    result = intake.check(edge)
    assert not (isinstance(result, str) and result.startswith("file too large"))


def _long_wav(path: Path, seconds: int) -> Path:
    """8 kHz, 8-bit mono WAV of ``seconds`` silence, streamed in 1 MB chunks."""
    rate = 8_000
    chunk = bytes(1_000_000)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.setnframes(rate * seconds)
        remaining = rate * seconds
        while remaining:
            n = min(remaining, len(chunk))
            wav.writeframesraw(chunk[:n])
            remaining -= n
    return path


def test_too_long_is_rejected(tmp_path):
    reason = _rejection(_long_wav(tmp_path / "long.wav", intake.MAX_SECONDS + 1))
    assert reason == "rejected: too long: 60.0 min (3,601.0 s), limit 60 min"


def test_at_duration_limit_is_accepted(tmp_path):
    path = _long_wav(tmp_path / "hour.wav", intake.MAX_SECONDS)
    assert intake.check(path) == ("wav", 3600.0, path.stat().st_size)


def test_large_file_checks_are_fast(tmp_path):
    started = time.perf_counter()
    _rejection(_sparse_wav(tmp_path / "big.wav", intake.MAX_BYTES + 1))
    intake.check(_sparse_wav(tmp_path / "edge.wav", intake.MAX_BYTES))
    _rejection(_long_wav(tmp_path / "long.wav", intake.MAX_SECONDS + 1))
    intake.check(_long_wav(tmp_path / "hour.wav", intake.MAX_SECONDS))
    assert time.perf_counter() - started < 2


class _Packet:
    def __init__(self, duration, time_base):
        self.duration, self.time_base = duration, time_base


class _NoDurationContainer:
    """A container with no duration whose audio packets add up to 2.5 s."""

    duration = None

    class streams:  # mimics PyAV's container.streams
        audio = ["stream"]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def demux(self, stream):
        from fractions import Fraction

        return [_Packet(1000, Fraction(1, 1000)), _Packet(1500, Fraction(1, 1000))]


def test_duration_falls_back_to_packet_sum(monkeypatch):
    monkeypatch.setattr("av.open", lambda *a, **k: _NoDurationContainer())
    assert intake.check(FIXTURES / "sample.wav") == (
        "wav",
        2.5,
        (FIXTURES / "sample.wav").stat().st_size,
    )


def test_rejected_file_never_reaches_transcription(tmp_path, monkeypatch):
    def no_transcriber(model_size):
        raise AssertionError("transcription ran for a rejected file")

    monkeypatch.setattr(asr, "get_transcriber", no_transcriber)
    fake = tmp_path / "fake.wav"
    fake.write_text("not audio")
    state = run_pipeline(str(fake))
    assert state["stages_completed"] == ["intake", "report"]
    assert state["status"] == "failed"
    assert state["status_reason"].startswith("rejected: unsupported format")
    assert state["transcript"] is None
    assert [(e.stage, e.outcome) for e in state["audit"]] == [
        ("intake", "failed"),
        ("report", "ok"),
    ]
    assert state["audit"][0].detail == state["status_reason"]
