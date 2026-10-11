---
title: 'Refactor sweep'
type: 'refactor'
ticket: '6'
created: '2026-10-11'
status: 'built'
baseline_revision: 'cf614821da4443c8ea0253abfaafb54e0b98216b'
route: 'oneshot'
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

**Problem:** `asr.load_channels` decodes a stereo file a second time, fully in memory (about 700 MB extra peak for a 60-minute call), only to compute per-segment channel loudness. Deferred from the 2.3 review.

**Approach:** Cleanup with no behavior change. `load_channels` keeps its interface but streams PyAV frames (resampled to 16 kHz float stereo) into a per-10 ms RMS envelope per channel, returned at rate 100. `label_segments` is unchanged: RMS over a window of equal-size window-RMS values equals the true RMS, so labels match up to 10 ms boundary rounding. The dual-mono check keeps its criterion (max absolute sample difference of at most 1e-3), tracked while streaming. Scope comes from `deferred-work.md`, whose only open entry this is; the CLI-exit entry was resolved by 2.5.

</frozen-after-approval>

## Implementation Notes

Oneshot: about 40 lines in `asr.py`, plus a memory regression test.

- `asr.load_channels` now streams `container.decode` frames through `AudioResampler(fltp, stereo, 16 kHz)` into per-10 ms mean squares, tracks the max absolute L-R sample difference for the dual-mono check (same 1e-3 criterion), and returns `sqrt` envelopes at `ENVELOPE_RATE = 100`. Interface and `speakers.label_segments` are unchanged.
- Measured on a 13-minute, 49.9 MB stereo WAV (the intake limit): traced peak 9.2 MB, against about 100 MB of floats (plus a 50 MB s16 buffer) for the old full decode. Envelope RMS matched sample RMS to 5 decimals.
- New `tests/unit/test_channel_envelope.py`: RMS equivalence on the fixture, and a memory bound (peak under a quarter of a full float decode for 3 minutes of stereo). 156 tests pass; both slow real-model labeling tests pass unchanged.
- `deferred-work.md`: appended a resolved line.

## Review Triage Log

Pass 1 (quick lens): high 0, medium 1, low 3, false 1, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `load_channels` decode loop | medium | patch | It no longer skipped `InvalidDataError` frames as `decode_audio` does, so one bad frame failed the run (a behavior change). Fix: `_valid_frames` mirrors faster-whisper's guard; a test injects a corrupt frame and asserts it is hit and does not raise. |
| 2 | `load_channels` docstring | low | patch | It claimed exact equivalence; now says "up to 10 ms boundary rounding" and notes the frame skipping. |
| 3 | module docstring | low | patch | Stale "decodes the separate channels"; now describes the envelope. |
| 4 | equivalence test windows | low | reject | Boundaries all fall on 10 ms; the plan accepts 10 ms rounding, and the slow real-model tests (pass, unchanged) cover label equivalence. |
| 5 | `deferred-work.md` outside the diff | false | reject | A one-line documentation note, not code under review. |
