---
title: 'Speaker labeling: pyannote vs. split by channel'
type: 'chore'
ticket: '2'
created: '2026-10-11'
status: 'built'
baseline_revision: '443c93cda8b695f0598d13d3516a84fe1bdf8014'
route: 'oneshot'
route_source: 'auto'
risk: 'medium'
review: 'none'
review_source: 'auto'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-2 needs speaker labels, faster-whisper has no diarization, and story 2.3 cannot be designed until the approach is chosen.

**Approach:** Desk comparison (user's choice, 2026-10-11). Prototype split-by-channel labeling on the fixtures and measure it; assess pyannote from its package metadata and dependency footprint without installing it. End with a recommendation for the user to decide.

</frozen-after-approval>

## Findings

**Split by channel, measured** on `call_stereo.wav` (14.4 s, 4 turns), whisper `tiny`, CPU int8, M-series Mac. Prototype in the session scratchpad; no repo code.

| Variant | Crosstalk | Segments | Correct labels | ASR time | Real-time factor |
|---|---|---|---|---|---|
| A: transcribe the mix once, label each segment by the louder channel in its time window | none | 4 | 4/4 | 0.71 s | 0.049 |
| B: transcribe each channel separately, merge by start time | none | 4 | 4/4 | 0.89 s | 0.062 |
| A | 30% bleed | 4 | 4/4 | 0.64 s | 0.045 |
| B | 30% bleed | **8** | every turn duplicated | 1.34 s | 0.093 |

- A is robust to crosstalk and needs one ASR pass. B transcribes the faint bleed as a second copy of every turn and doubles ASR cost. **A is the channel variant to use.**
- Channel labeling cannot separate speakers in mono audio: `call_mono.wav` would come out as one speaker.
- No new dependencies: numpy and PyAV already come with faster-whisper.

**pyannote.audio, desk assessment** (resolved with `uv pip compile` on 2026-10-11; not installed or run):
- Latest is 4.0.7. It resolves to **94 packages**, compared with 23 for faster-whisper, including torch 2.14.1, torchaudio, lightning, and asteroid.
- torch wheel: 127 MB on macOS arm64, 555 MB on Linux x86_64. **On Linux it also pulls 15 `nvidia-*` CUDA packages**, so CI downloads grow by gigabytes unless the CPU-only torch index is configured.
- Its pretrained pipelines are gated on Hugging Face: they need a token and acceptance of the model terms, so CI and every developer need that setup.
- It works on mono and on overlapping speech, which channel splitting cannot. Accuracy and CPU speed were **not measured** in this spike.

## Recommendation

Use **split by channel, variant A**, for story 2.3:
- Exact on stereo call recordings, which is the common call-center format, and robust to crosstalk.
- About a 5% real-time factor on CPU with `tiny`, and zero new dependencies, keeping CI small and token-free.
- Mono files get a single label, with the audit detail saying no speaker separation was possible.

Revisit pyannote only if real demo recordings turn out to be mono. It could then be an optional extra rather than a core dependency.

## Implementation Notes

Spike only: no production code changed. The findings above are the deliverable; the user's decision is recorded in the epic's Notes.

- User decision (2026-10-11): option (a), split by channel variant A with `agent`/`customer` labels and a configurable channel mapping. Recorded in the epic's Notes; the `unknown` on 2.3 is removed.
