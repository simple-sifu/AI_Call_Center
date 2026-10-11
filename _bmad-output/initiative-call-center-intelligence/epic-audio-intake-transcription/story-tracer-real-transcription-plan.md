---
title: 'Tracer: real transcription'
type: 'feature'
ticket: '1'
created: '2026-10-11'
status: 'built'
baseline_revision: 'd23089eaade67cb307a1ff3af6f4c7318914527c'
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

**Problem:** The transcription stage is a stub, so no real speech enters the pipeline and the risky parts (model loading, CPU speed, the transcript shape) are untested.

**Approach:** Put faster-whisper behind a small `Transcriber` interface and have the transcription stage produce a real `Transcript` from the audio file, using `WHISPER_MODEL_SIZE`. Every segment gets the label `speaker_1` until story 2.3. Add say-generated two-voice fixtures. Tests use a fake transcriber by default; one opt-in `slow` test runs the real `tiny` model.

## Boundaries & Constraints

**Always:**
- CPU only: `device="cpu"`, `compute_type="int8"`. The model size comes from `Settings.whisper_model_size`.
- The model loads lazily on first use and is reused within a process (one per size).
- `audio_sha256` is the real SHA-256 of the file bytes.
- No test run by default or in CI loads a real model: `addopts` excludes `slow`, and an autouse fixture swaps in a fake transcriber for every test not marked `slow`.
- The stage still emits one `ok` AuditEvent, and the rest of the contract is unchanged.

**Never:** speaker labeling beyond `speaker_1` (2.2–2.3); a cache (2.4); intake validation (2.5); changes to `models.py`, `state.py`, or other stages.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fake transcriber | any file; fake returns 2 segments | `Transcript` with 2 segments, both `speaker_1`, times and text preserved, `audio_sha256` = file hash | No error expected |
| No speech | fake returns no segments (e.g. the tone `sample.wav`) | `Transcript` with `segments=()` | No error expected |
| Model size | `WHISPER_MODEL_SIZE=base` | the transcriber is built with `base` | No error expected |
| Real model (slow) | `call_stereo.wav`, size `tiny` | the joined text contains "thank" and "calling" (case-insensitive); segment times non-decreasing | No error expected |
| Transcriber raises | fake raises `RuntimeError("decode failed")` | status `failed`, `status_reason` names the error, a `failed` audit event at transcription, run skips to report | No exception escapes the graph |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/transcription.py` -- stub returning `_PLACEHOLDER`; replace with real logic, keeping `NAME` and `run(state) -> dict`.
- `src/call_center/models.py` -- `Transcript(segments, audio_sha256)` and `TranscriptSegment(speaker, start, end, text)`; read-only for this story.
- `src/call_center/config.py` -- `load_settings()` and `Settings.whisper_model_size` (default `tiny`).
- `src/call_center/graph.py` -- the halted-status router already skips to report on `failed`; no change.
- `tests/conftest.py` -- folder markers plus the `_isolated_config` autouse fixture; add the fake-transcriber fixture here.
- `tests/fixtures/` -- `sample.wav` (a tone) and `make_sample.py`. macOS `say` has voices Samantha (en_US) and Daniel (en_GB); `say --data-format=LEI16@16000 -o f.wav` writes WAV directly.
- `pyproject.toml` -- add `faster-whisper` (it brings PyAV, ctranslate2 and onnxruntime, but no torch); add the `slow` marker and `-m "not slow"` to `addopts` (a later `-m slow` on the command line overrides it).

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- `uv add faster-whisper`; register the `slow` marker; `addopts = "--strict-markers -m 'not slow'"`.
- [x] `src/call_center/asr.py` -- `RawSegment(start, end, text)` dataclass; `Transcriber` Protocol with `transcribe(path) -> list[RawSegment]`; `FasterWhisperTranscriber(model_size)` wrapping `WhisperModel(..., device="cpu", compute_type="int8")`, loaded lazily; `get_transcriber(model_size)`, cached per size.
- [x] `src/call_center/stages/transcription.py` -- read the file, hash it, call `get_transcriber(load_settings().whisper_model_size)`, and map segments to a `Transcript` with `speaker_1`. On an exception, return status `failed`, a reason, and a `failed` AuditEvent.
- [x] `tests/fixtures/make_call.py`, `call_stereo.wav`, `call_mono.wav` -- `say` renders 4 alternating turns (agent: Samantha, left channel; customer: Daniel, right channel; silence on the other channel during each turn); mono is the mix. The first agent line contains "Thank you for calling". Commit the generated files (under about 1.5 MB in total).
- [x] `tests/conftest.py` -- autouse fixture: unless the test is marked `slow`, monkeypatch `call_center.asr.get_transcriber` to return a fake that yields no segments.
- [x] `tests/unit/test_transcription.py` -- matrix rows 1, 2, 3 and 5.
- [x] `tests/integration/test_transcription_real.py` -- matrix row 4, `@pytest.mark.slow`.

**Acceptance Criteria:**
- Given a fresh clone, when `uv run pytest` runs (as CI does), then no model is downloaded and all tests pass.
- Given the user's machine, when `uv run pytest -m slow` runs for the first time, then the `tiny` model downloads once (hitl) and the slow test passes.
- Given `call_stereo.wav`, when `uv run call-center analyze tests/fixtures/call_stereo.wav` runs, then it exits 0.

## Implementation Notes

- The stage calls `asr.get_transcriber(...)` through the module so the conftest monkeypatch takes effect. Segment times are clamped (`start >= 0`, `end >= start`) so a Whisper timing quirk cannot fail model validation.
- Any exception (including an unreadable file) becomes status `failed`; the failed update still lists the stage in `stages_completed`.
- `tests/security/test_blocked_run.py` now creates its `call.wav` (empty) because transcription reads the file; with the old missing path the run correctly failed at transcription instead of reaching the patched injection stage.
- Fixtures: `call_stereo.wav` 924 KB + `call_mono.wav` 462 KB (14.4 s). Real `tiny` output on stereo: 4 segments, first "Thank you for calling Agme Support...".

## Plan Change Log

- 2026-10-11: added a direct `av>=11,<19` pin. PyAV 19 removed `av.open(metadata_errors=...)`, which faster-whisper 1.2.1 passes, so every real transcription failed with `TypeError`.

## Review Triage Log

Pass 1 (quick lens): high 0, medium 1, low 5, false 0, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `transcription.py` except block | low | patch | A `ValidationError` from `load_settings()` puts `input_value` and a docs URL in `status_reason`, labelled as a transcription failure. Fix: catch it separately and use `format_config_error`. |
| 2 | `cli.py` / AC 3 | medium | defer | The CLI exits 0 on a `failed` run, so AC 3 cannot catch a broken stage. Deferred to story 2.5, which owns CLI rejection exits (`deferred-work.md`). |
| 3 | `pyproject.toml` addopts | low | patch | A command-line `-m integration` replaces `-m 'not slow'` and loads the real model. Fix: deselect `slow` in the collection hook unless `-m` names it. |
| 4 | real-model test | low | reject | Sorted starts plus `end >= start` satisfies "non-decreasing"; a stricter cross-segment check risks flakiness on real whisper output. |
| 5 | `test_no_speech_gives_empty_segments` | low | patch | Depends on the conftest default fake. Fix: install its own empty fake. |
| 6 | `path.read_bytes()` hashing | low | patch | Whole-file read for hashing; `hashlib.file_digest` is a direct fix (files are capped at 50 MB, so impact is small). |

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, slow test deselected, no model download
- `uv run pytest -m slow` -- expected: real `tiny` transcription passes (first run downloads the model)
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
