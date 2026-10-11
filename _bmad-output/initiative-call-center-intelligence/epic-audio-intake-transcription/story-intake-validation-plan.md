---
title: 'Intake validation'
type: 'feature'
ticket: '5'
created: '2026-10-11'
status: 'built'
baseline_revision: '0b55a84d9c8bdb624f3e3aba7b375f7ae8fad569'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Intake is a stub, so any file, of any size or length, goes straight to whisper. The CLI also exits 0 when a run fails (deferred from the 2.1 review), which hides broken runs.

**Approach:** Make intake real. It checks the size first, then detects the format from magic bytes, then confirms an audio stream and measures duration with PyAV. A rejection sets status `failed` with `status_reason` = `rejected: <why>` and a `failed` audit event, and the graph skips to the report. The CLI still writes the report, but for a `failed` or `blocked` run it prints the reason to stderr and exits 2.

## Boundaries & Constraints

**Always:**
- Limits: size at most 50 MiB (52,428,800 bytes); duration at most 60 minutes (3,600 s). Exactly at a limit is accepted.
- Check order: size (stat only, nothing read), then magic bytes (the first 12 bytes), then PyAV open and duration. The cheapest check rejects first.
- Accepted magic: WAV `RIFF`....`WAVE`; FLAC `fLaC`; OGG `OggS`; MP3 `ID3`, or a frame sync (first byte `0xFF`, top 3 bits of the second byte set); M4A `ftyp` at offset 4. The file extension is never consulted.
- Duration comes from the container; if that is missing, sum the audio packet durations (demux only, no decode).
- On success the audit detail reads like `wav, 14.4 s, 0.9 MB`.
- CLI stderr for a failed run is the `status_reason` as-is (e.g. `rejected: file too large: …` or `transcription failed: …`); for a blocked run it is `blocked: <reason>`. The existing pre-run checks (config, missing file, not a file) keep their messages and exit 2.

**Never:** trusting the extension; reading a whole file to check its size; changing the report JSON shape (Epic 5); touching other stages.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Each format | 1 s tone as WAV, MP3, FLAC, OGG, M4A | accepted; audit detail names the format and about 1.0 s | No error expected |
| Renamed text file | `notes.txt` content saved as `fake.wav` | rejected: `unsupported format` (content check) | status `failed`, skip to report |
| Valid magic, corrupt body | `RIFF....WAVE` then garbage | rejected: `unreadable audio` | same |
| Too large | sparse file of 52,428,801 bytes with a WAV header | rejected: `file too large` with size and limit; body never read | same |
| At size limit | exactly 52,428,800 bytes | not rejected for size (it may still fail a later check) | — |
| Too long | 8 kHz 8-bit mono WAV of 3,601 s (about 28.8 MB) | rejected: `too long` with minutes and limit | same |
| At duration limit | the same at exactly 3,600 s | accepted | No error expected |
| CLI on rejection | `call-center analyze fake.wav` | report JSON still written; stderr `rejected: unsupported format…`; exit 2 | — |
| CLI on blocked or other failure | a run ending `blocked`, or `failed` at transcription | stderr `blocked: <reason>` or the transcription reason; exit 2 | — |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/intake.py` -- stub: `NAME = "intake"`, `run(state)` returns an `ok` audit. Replace it; keep the `stages_completed` entry on both paths.
- `src/call_center/graph.py` -- the router already skips to `report` when status is `failed`; no change.
- `src/call_center/asr.py` -- `load_channels` shows the PyAV pattern: `av.open(str(path), metadata_errors="ignore")`, `container.streams.audio[0]`. Reuse it.
- `src/call_center/cli.py` -- after `run_pipeline`, the report is written and the CLI returns 0. Add the status check after writing the report. Pre-run checks stay above.
- `tests/integration/test_pipeline.py` -- CLI tests call `main([...])` with `tmp_path`; `test_cli_happy_path_writes_report` uses `sample.wav` (a valid WAV, so still accepted).
- `tests/security/test_blocked_run.py` -- writes a short silent mono WAV; still valid.
- `tests/fixtures/` -- `sample.wav`, `call_stereo.wav`, `call_mono.wav`, and their generators. `ffmpeg` is available locally, not in CI.
- `_bmad-output/initiative-call-center-intelligence/deferred-work.md` -- this story closes the first entry (CLI exit code).

## Tasks & Acceptance

**Execution:**
- [x] `tests/fixtures/make_formats.sh`, `tone.mp3`, `tone.flac`, `tone.ogg`, `tone.m4a` -- `ffmpeg -f lavfi -i sine=frequency=440:duration=1:sample_rate=16000 -ac 1`; commit the outputs (about 31 KB total).
- [x] `src/call_center/stages/intake.py` -- `detect_format(header: bytes) -> str | None`; `check(path) -> (format, seconds, size)` or a rejection reason; `run` sets `failed` and `rejected: …` on rejection, otherwise an `ok` audit with the detail.
- [x] `src/call_center/cli.py` -- after writing the report, if status is `failed` print `status_reason`; if `blocked` print `blocked: <reason>`; in both cases return 2.
- [x] `tests/unit/test_intake.py` -- every magic-byte case, including an MP3 frame sync without ID3, and matrix rows 1–7. Large and long files are generated in `tmp_path`: sparse via `truncate` for size; streamed zeros for duration.
- [x] `tests/integration/test_pipeline.py` -- matrix rows 8–9, with transcription made to fail or injection made to block via monkeypatch.
- [x] `deferred-work.md` -- mark the CLI-exit entry resolved by this story (append a line; do not edit the entry).

**Acceptance Criteria:**
- Given any rejected file, when the pipeline runs, then transcription never runs (no transcriber call) and the report stage still records the reason in the audit trail.
- Given the default `uv run pytest`, when it runs, then it stays fast (the large-file tests take under 2 s in total) and needs no ffmpeg.

## Implementation Notes

- `intake.check` returns `(format, seconds, size)` or a reason string; `run` prefixes `rejected: `. Reasons: `file too large: N bytes (limit 52,428,800 bytes)`, `unsupported format: …`, `unreadable audio: <PyAV strerror>` (also `no audio stream`, `duration unknown`), `too long: 60.0 min (3,601.0 s), limit 60 min`, and `unreadable file: …` for a stat/open error (e.g. a missing file when a stage is called directly).
- Success detail size uses decimal MB (`size / 1e6`), matching the `0.9 MB` example.
- `make_formats.sh` passes `-map_metadata -1` so the fixtures carry no encoder metadata; outputs total about 31 KB.
- The packet-sum fallback is unit-tested with a fake container (no committed fixture lacks a container duration).

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 0, low 5, false 1, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | fixtures missing from the diff | false | reject | The binaries were left out of the review diff on purpose; they are untracked and not ignored, and are committed with the story. CI on the PR confirms it. |
| 2 | `make_formats.sh` encoder tags | low | patch | `-map_metadata -1` left Lavf/Lavc tags in. Added `-fflags +bitexact -flags:a +bitexact -write_id3v2 0` and regenerated; `strings` now finds no Lavf/Lavc tags. |
| 3 | AC 1, report stage records the reason | low | reject | The reason is in the audit trail (the intake event) and the report stage still runs. The report stage is a stub until Epic 5, and this story must not touch other stages. |
| 4 | MP3 sync matches the UTF-16 BOM | low | reject | The file is still rejected (`unreadable audio` rather than `unsupported format`); only the message differs, and the fix adds header-bit parsing. |
| 5 | detected format not passed to PyAV | low | reject | An MP4 with audio is accepted as `m4a`; harmless, since its audio transcribes. The plan does not require matching. |
| 6 | `cli.py` `blocked: None` | low | patch | Latent; the fallback is now `no reason given`. |

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
