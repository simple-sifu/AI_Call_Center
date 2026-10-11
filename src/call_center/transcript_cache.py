"""File cache of raw ASR segments, keyed by the audio's SHA-256 and the model size.

An entry lives at ``<cache_dir>/<sha256>/<model_size>.json`` and holds only the schema
version and the raw segments (start, end, text): never speaker labels, settings, or the
source path, so labelling re-runs on every hit. Entries hold unredacted call text, so
they are created owner-only (files ``0600``, directories ``0700``). Writes are atomic.
Any unreadable, corrupt, or wrong-version entry is a miss; nothing here raises.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from call_center.asr import RawSegment

SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MODEL_SIZE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def entry_path(cache_dir: str | Path, sha256: str, model_size: str) -> Path:
    """Where the entry for ``sha256`` and ``model_size`` lives; rejects unsafe keys."""
    if not _SHA256.fullmatch(sha256):
        raise ValueError("sha256 must be 64 lowercase hex characters")
    if not _MODEL_SIZE.fullmatch(model_size) or ".." in model_size:
        raise ValueError("invalid model size for a cache key")
    return Path(cache_dir) / sha256 / f"{model_size}.json"


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _parse(data: object) -> list[RawSegment] | None:
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        return None
    items = data.get("segments")
    if not isinstance(items, list):
        return None
    segments = []
    for item in items:
        if not isinstance(item, dict):
            return None
        start, end, text = item.get("start"), item.get("end"), item.get("text")
        if not (_number(start) and _number(end) and isinstance(text, str)):
            return None
        segments.append(RawSegment(start=float(start), end=float(end), text=text))
    return segments


def load(cache_dir: str | Path, sha256: str, model_size: str) -> list[RawSegment] | None:
    """The cached segments, or ``None`` on a miss (absent, unreadable, corrupt, old)."""
    try:
        path = entry_path(cache_dir, sha256, model_size)
        with path.open("r", encoding="utf-8") as entry:
            return _parse(json.load(entry))
    except Exception:  # a cache must never fail the run: any bad entry is a miss
        # (beyond OSError/ValueError: OverflowError from huge ints, RecursionError from
        # deep nesting)
        return None


def _make_private_dirs(directory: Path) -> None:
    """Create ``directory`` and any missing ancestors as ``0700``."""
    missing = []
    current = directory
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for path in reversed(missing):
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            continue  # created concurrently; leave its mode to its creator
        os.chmod(path, 0o700)  # mkdir's mode is narrowed by the umask, never widened


def store(cache_dir: str | Path, sha256: str, model_size: str, segments: list[RawSegment]) -> bool:
    """Write the entry atomically; ``True`` if written, ``False`` if the write failed."""
    tmp_name = None
    try:
        path = entry_path(cache_dir, sha256, model_size)
        _make_private_dirs(path.parent)
        payload = {
            "version": SCHEMA_VERSION,
            "segments": [
                {"start": float(s.start), "end": float(s.end), "text": str(s.text)}
                for s in segments
            ],
        }
        # mkstemp creates the file 0600 in the entry's own directory, so the replace
        # below is a same-filesystem rename.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
