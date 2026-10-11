---
title: 'Speaker labeling'
type: 'feature'
ticket: '3'
created: '2026-10-11'
status: done
baseline_revision: '335a6590bde370ab2e97252f61855b05000ac20a'
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

**Problem:** Every transcript segment is labeled `speaker_1`, so CAP-2's speaker-labeled transcript is not met and later QA scoring cannot tell the agent from the customer.

**Approach:** Implement spike 2.2's variant A. Transcription stays a single pass over the mix. For stereo audio, each segment is then labeled by whichever channel is louder (RMS) within its time window: `agent` for the configured agent channel (default left), `customer` for the other. Mono audio keeps one label, `speaker_1`, and its audit detail says no speaker separation was possible.

## Boundaries & Constraints

**Always:**
- Labeling is a pure function in its own module, testable with synthetic arrays and no model.
- The real channel count comes from the file's audio stream (PyAV), never from `decode_audio(split_stereo=True)`, because that upmixes mono to two identical channels.
- `AGENT_CHANNEL` setting: `left` or `right`, default `left`; invalid values fail through the existing `invalid configuration:` path.
- Ties (equal RMS, including silence on both channels) go to the agent channel.
- More than 2 channels is treated like mono: one label, with an audit note naming the channel count.
- The transcriber is still called once per file.

**Never:** pyannote or any new dependency; changes to `models.py` or `state.py`; the transcript cache (2.4); intake validation (2.5).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Stereo, clean | left loud during segment 1, right loud during segment 2 | labels `agent`, `customer` | No error expected |
| Stereo, 30% crosstalk | each channel carries 30% of the other | same labels as clean | No error expected |
| Agent on right | `AGENT_CHANNEL=right`, same audio | labels `customer`, `agent` | No error expected |
| Tie / silence | both channels zero in a segment's window | label `agent` | No error expected |
| Mono | 1-channel file | every segment `speaker_1`; audit detail contains `mono: no speaker separation` | No error expected |
| Real call (slow) | `call_stereo.wav`, plus a 30% crosstalk copy made in `tmp_path`, model `tiny` | `agent, customer, agent, customer` for both | No error expected |
| Invalid setting | `AGENT_CHANNEL=middle` | run `failed`; reason starts `invalid configuration:` and names `AGENT_CHANNEL` | No exception escapes |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/transcription.py` -- currently: hash with `hashlib.file_digest`, `load_settings()` in its own `try` (ValidationError → `invalid configuration:` via `_failed`), `asr.get_transcriber(...).transcribe(path)`, `_segment(raw)` with fixed `SPEAKER = "speaker_1"`. Insert labeling between transcribe and building segments.
- `src/call_center/asr.py` -- `RawSegment(start, end, text)`; add channel loading here (it already owns audio I/O).
- `faster_whisper.decode_audio(path, sampling_rate=16000, split_stereo=True)` returns `(left, right)` float32 arrays. Use it only after confirming the stream has 2 channels via `av.open(path).streams.audio[0].channels`.
- `src/call_center/config.py` -- add `agent_channel: Literal["left", "right"] = "left"` with alias `AGENT_CHANNEL`. `ENV_VARS` and `format_config_error` pick it up automatically.
- `.env.example` -- add `AGENT_CHANNEL=left` with a comment.
- `tests/conftest.py` -- the autouse fake transcriber returns no segments; tests that need segments install their own fake (see `use_fake` in `tests/unit/test_transcription.py`).
- `tests/fixtures/call_stereo.wav` (agent left, customer right, 4 turns) and `call_mono.wav`.
- `_bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md` -- the Boundaries touch point still says "and the diarization tool, if one is chosen"; drop that phrase.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/speakers.py` -- `label_segments(segments, channels, rate, agent_channel) -> list[str]`: per-segment RMS over `[start, end)` on each channel, louder channel wins, ties go to agent; with fewer or more than 2 channels, every label is `speaker_1`.
- [x] `src/call_center/asr.py` -- `load_channels(path) -> tuple[list[np.ndarray], int, int]` (arrays, rate, source channel count): stereo returns the two 16 kHz arrays; any other count returns `[]` plus that count.
- [x] `src/call_center/config.py`, `.env.example` -- the `AGENT_CHANNEL` setting.
- [x] `src/call_center/stages/transcription.py` -- load channels, label segments, put the label on each `TranscriptSegment`; audit detail `"<n> segments; stereo, agent=<left|right>"` or `"<n> segments; mono: no speaker separation"` (or `"<k> channels: no speaker separation"`).
- [x] `tests/unit/test_speakers.py` -- matrix rows 1–4 and the more-than-2-channels case, with synthetic numpy arrays.
- [x] `tests/unit/test_transcription.py` -- stage-level rows 5 and 7 (with a fake transcriber on `call_mono.wav`), plus a stereo case on a small synthetic stereo WAV written to `tmp_path`.
- [x] `tests/integration/test_transcription_real.py` -- row 6 (`slow`); update the existing slow test's `speaker_1` assertion to the new labels.
- [x] Initiative file -- drop the stale diarization phrase from the touch point.

**Acceptance Criteria:**
- Given the default `uv run pytest`, when it runs, then no model loads and all tests pass.
- Given `call_stereo.wav`, when the pipeline runs with the real `tiny` model, then the transcript's speakers read `agent, customer, agent, customer`.

## Implementation Notes

- `tests/security/test_blocked_run.py` wrote an empty `call.wav`; transcription now opens the audio stream to count channels, so an undecodable file fails the stage. The test now writes a short silent mono WAV instead.
- Channel-loading errors (e.g. an undecodable file) go through the existing `transcription failed:` path; the transcriber is still called once, before channels are loaded.
- Stereo files with identical channels (dual-mono) are treated as unseparated: `speaker_1` and audit `"<n> segments; dual-mono: no speaker separation"` (review follow-up).
- `av.open` uses `metadata_errors="ignore"` to match faster-whisper's decode (review follow-up).
- `numpy` and `av` are imported directly but were already installed via `faster-whisper`; no dependency was added to `pyproject.toml`.
- Review patches: `load_channels` opens with `metadata_errors="ignore"`; dual-mono stereo (channels equal within 1e-3, about -60 dBFS, so lossy-codec noise still counts) is treated as unseparated with audit `dual-mono: no speaker separation`; `numpy` is declared directly. That respects the "no new dependency" rule's intent (no new package; it was already installed via faster-whisper), as with `langchain-core` in story 1.5.
- Deferred to the 2.6 sweep: the second full-memory decode of stereo files (`deferred-work.md`).
- Verified: 88 tests pass on 3.12 and 3.11; both slow real-model tests pass (`agent, customer, agent, customer`, with and without 30% crosstalk); ruff is clean.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens, plus one lead check): high 0, medium 2, low 2, false 0, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `asr.load_channels` open options | low | patch | Opens without `metadata_errors="ignore"`, unlike faster-whisper's decode, so a bad-metadata file transcribes then fails. Fix: match the option. |
| 2 | dual-mono stereo | medium | patch | Identical channels tie on every segment, so all become `agent` and the audit claims separation. Fix: treat equal channels as unseparated, with a `dual-mono` audit note. |
| 3 | `load_channels` second full decode | medium | defer | About 700 MB extra peak for a 60-minute stereo call. The fix needs a streaming design, which is not a trivial patch; deferred to the 2.6 sweep (`deferred-work.md`) with the user told. Typical calls are minutes, so a few MB. |
| 4 | `numpy` undeclared (lead check) | low | patch | Imported directly but only transitive. Fix: `uv add numpy`. |

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, slow deselected
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: real-model labeling passes, including with crosstalk
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
