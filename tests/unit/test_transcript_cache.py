import json
import os

import pytest

from call_center import transcript_cache
from call_center.asr import RawSegment

SHA = "ab" * 32
SEGMENTS = [RawSegment(0.0, 1.25, "Thank you for calling."), RawSegment(1.25, 2.5, "Hi.")]


def test_missing_entry_is_a_miss(tmp_path):
    assert transcript_cache.load(tmp_path, SHA, "tiny") is None


def test_round_trip(tmp_path):
    assert transcript_cache.store(tmp_path, SHA, "tiny", SEGMENTS) is True
    assert transcript_cache.load(tmp_path, SHA, "tiny") == SEGMENTS
    assert transcript_cache.load(tmp_path, SHA, "base") is None
    assert (tmp_path / SHA / "tiny.json").is_file()


def test_empty_segments_round_trip_as_a_hit(tmp_path):
    transcript_cache.store(tmp_path, SHA, "tiny", [])
    assert transcript_cache.load(tmp_path, SHA, "tiny") == []


def test_entry_holds_only_version_and_raw_segments(tmp_path):
    transcript_cache.store(tmp_path, SHA, "tiny", SEGMENTS)
    data = json.loads((tmp_path / SHA / "tiny.json").read_text())
    assert data == {
        "version": transcript_cache.SCHEMA_VERSION,
        "segments": [
            {"start": 0.0, "end": 1.25, "text": "Thank you for calling."},
            {"start": 1.25, "end": 2.5, "text": "Hi."},
        ],
    }


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "",
        b"\xff\xfe\x00garbage",
        json.dumps({"version": 999, "segments": []}),
        json.dumps({"segments": []}),
        json.dumps([1, 2]),
        json.dumps({"version": 1, "segments": "nope"}),
        json.dumps({"version": 1, "segments": [{"start": 0, "end": 1}]}),
        json.dumps({"version": 1, "segments": [{"start": True, "end": 1, "text": "x"}]}),
    ],
)
def test_corrupt_or_wrong_version_is_a_miss_and_overwritten(tmp_path, content):
    entry = tmp_path / SHA / "tiny.json"
    entry.parent.mkdir()
    if isinstance(content, bytes):
        entry.write_bytes(content)
    else:
        entry.write_text(content)

    assert transcript_cache.load(tmp_path, SHA, "tiny") is None
    assert transcript_cache.store(tmp_path, SHA, "tiny", SEGMENTS) is True
    assert transcript_cache.load(tmp_path, SHA, "tiny") == SEGMENTS


def test_unreadable_entry_is_a_miss(tmp_path):
    entry = tmp_path / SHA / "tiny.json"
    entry.parent.mkdir()
    entry.mkdir()  # a directory where the file should be
    assert transcript_cache.load(tmp_path, SHA, "tiny") is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_dir_returns_false_without_raising(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    try:
        assert transcript_cache.store(locked, SHA, "tiny", SEGMENTS) is False
        assert transcript_cache.load(locked, SHA, "tiny") is None
    finally:
        locked.chmod(0o700)


def test_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(transcript_cache.os, "replace", boom)
    assert transcript_cache.store(tmp_path, SHA, "tiny", SEGMENTS) is False
    assert list((tmp_path / SHA).iterdir()) == []


def test_permissions_are_owner_only(tmp_path):
    cache_dir = tmp_path / "a" / "b"
    old = os.umask(0o000)  # even a permissive umask must not widen the modes
    try:
        transcript_cache.store(cache_dir, SHA, "tiny", SEGMENTS)
    finally:
        os.umask(old)
    assert (cache_dir / SHA / "tiny.json").stat().st_mode & 0o777 == 0o600
    for directory in (cache_dir / SHA, cache_dir, tmp_path / "a"):
        assert directory.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(("sha", "size"), [("../" * 3, "tiny"), (SHA, "../x"), ("AB" * 32, "tiny")])
def test_unsafe_keys_are_rejected(tmp_path, sha, size):
    with pytest.raises(ValueError):
        transcript_cache.entry_path(tmp_path, sha, size)
    assert transcript_cache.load(tmp_path, sha, size) is None
    assert transcript_cache.store(tmp_path, sha, size, SEGMENTS) is False


@pytest.mark.parametrize(
    "content",
    [
        '{"version": 1, "segments": [{"start": 1' + "0" * 400 + ', "end": 1, "text": "x"}]}',
        "[" * 100_000 + "]" * 100_000,
    ],
    ids=["huge-int-overflow", "deep-nesting-recursion"],
)
def test_pathological_entries_are_misses(tmp_path, content):
    sha = "a" * 64
    path = transcript_cache.entry_path(tmp_path, sha, "tiny")
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert transcript_cache.load(tmp_path, sha, "tiny") is None
