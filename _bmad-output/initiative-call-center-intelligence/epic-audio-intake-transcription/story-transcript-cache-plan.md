---
title: 'Transcript cache'
type: 'feature'
ticket: '4'
created: '2026-10-11'
status: 'built'
baseline_revision: 'f67e09645c4be3154463a1c4fa618405906f8349'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every run re-transcribes the audio, which takes minutes for a long call on CPU, although CAP-2 says identical audio returns instantly.

**Approach:** Before transcribing, look up the raw whisper segments by the audio's SHA-256 plus the model size in a file cache, and store them after a miss. Speaker labeling re-runs on every hit, so a changed `AGENT_CHANNEL` never returns stale labels.

## Boundaries & Constraints

**Always:**
- Cache key: `<audio_sha256>` plus model size. Path: `<cache_dir>/<sha256>/<model_size>.json`.
- The cache holds the raw ASR segments only (start, end, text) with a schema version; never labels, settings, or the source path.
- Writes are atomic (a temp file in the same directory, then `os.replace`). An unreadable, corrupt, or wrong-version entry is a miss and is overwritten; it never fails the run.
- `TRANSCRIPT_CACHE_DIR` setting, default `.cache/transcripts` (relative to the working directory). `.cache/` is git-ignored.
- The audit detail says `cache hit`, `cache miss`, or `cache off`.
- Tests never write to the repo: an autouse fixture points `TRANSCRIPT_CACHE_DIR` at `tmp_path`.

**Never:** caching labels or `Transcript` objects; SQLite (Epic 5); changing `models.py` or `state.py`.

**Decisions (user, 2026-10-11):**
- The cache stores unredacted ASR text locally. Entries are created owner-only (file `0600`, directories `0700`), `.cache/` is git-ignored, and `TRANSCRIPT_CACHE` (`on` | `off`, default `on`) disables the cache entirely: no reads and no writes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First run | new audio | transcriber called once; entry written; audit `cache miss` | No error expected |
| Same audio again | byte-identical file (any name or path) | transcriber not called; same transcript; audit `cache hit` | No error expected |
| Other model size | same audio, `WHISPER_MODEL_SIZE=base` | miss; transcriber called | No error expected |
| Channel setting changed | cached stereo audio, then `AGENT_CHANNEL=right` | hit, and labels follow the new setting | No error expected |
| Corrupt entry | garbage JSON or wrong schema version on disk | treated as a miss; transcribed; entry rewritten | No exception |
| Cache off | `TRANSCRIPT_CACHE=off`, audio run twice | transcriber called both times; nothing written; audit `cache off` | No error expected |
| Permissions | first run writes an entry | entry file mode `0600`, its directories `0700` | No error expected |
| Cache dir unwritable | write fails | run still succeeds; audit notes `cache write failed` | No exception |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/transcription.py` -- `run`: loads settings, hashes the file with `hashlib.file_digest`, then `transcriber.transcribe(path)`, `load_channels`, `label_segments`. Insert the cache lookup and store around `transcribe` only.
- `src/call_center/asr.py` -- `RawSegment(start, end, text)` frozen dataclass; serialize this.
- `src/call_center/config.py` -- add `transcript_cache_dir: Path` (alias `TRANSCRIPT_CACHE_DIR`), plus `transcript_cache: Literal["on", "off"] = "on"` (alias `TRANSCRIPT_CACHE`).
- `tests/conftest.py` -- autouse fixtures for config isolation and the fake transcriber; add one for the cache dir.
- `tests/unit/test_transcription.py` -- `use_fake` and `_Fake` (records `paths`) are reusable for counting calls.
- `.gitignore`, `.env.example` -- add `.cache/` and the new variables.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/transcript_cache.py` -- `load(cache_dir, sha256, model_size) -> list[RawSegment] | None` and `store(...)` with the version, atomic write, and owner-only permissions.
- [x] `src/call_center/config.py`, `.env.example`, `.gitignore` -- the settings and the ignore rule.
- [x] `src/call_center/stages/transcription.py` -- look up before transcribing, store after a miss, and add `cache hit`, `cache miss`, or `cache off` to the audit detail.
- [x] `tests/conftest.py` -- autouse cache dir under `tmp_path`.
- [x] `tests/unit/test_transcript_cache.py` -- round trip, corrupt and wrong-version entries, unwritable dir, permissions.
- [x] `tests/unit/test_transcription.py` -- matrix rows 1–4, 6, 7 and 8 at stage level.

**Acceptance Criteria:**
- Given one audio file run twice, when the second run happens, then the transcriber is never called and the transcript is identical.
- Given the default test run, when it finishes, then nothing has been written under the repository's `.cache/`.

## Implementation Notes

- The cache note is the last `; `-separated part of the audit detail, e.g. `2 segments; stereo, agent=left; cache hit`. A failed write gives `...; cache miss; cache write failed`.
- `store` returns `False` instead of raising on any write failure; `load` returns `None` for absent, unreadable, corrupt, or wrong-version entries. Keys are validated (64 lowercase hex, plain model-size token) so a key can never escape the cache dir.
- Only missing directories are created (each `0700`, chmod after mkdir so the umask cannot matter); an existing user-chosen cache dir keeps its mode. The temp file comes from `mkstemp` (`0600`) in the entry's directory, then `os.replace`.
- On a hit the transcriber is not even constructed. `TRANSCRIPT_CACHE=off` skips both `load` and `store` and creates no directories.
- The `_isolated_transcript_cache` autouse fixture depends on `_isolated_config` (which clears every `ENV_VARS` name, now including the two cache variables) and sets `TRANSCRIPT_CACHE_DIR` to `tmp_path/transcript-cache`; it applies to slow tests too.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 0, low 1, false 0, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `transcript_cache.load` / `_parse` | low | patch | Reproduced: a huge int (OverflowError) or 100k-deep nesting (RecursionError) escaped `load` and failed the run, against "never fails the run". Fix: `load` catches every exception and returns a miss; two pathological tests added. 152 tests pass. |

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass; `.cache/` in the repo untouched
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
