---
type: epic
title: "Audio intake and transcription"
parent: initiative-call-center-intelligence
covers: [CAP-1, CAP-2]
after: []
assignee: ""
risk: high
---

# Audio intake and transcription

## Description

Real stages 1 and 2: validate uploaded audio by content and limits, then produce a speaker-labeled transcript, cached by the audio's hash.

## Outcome

Any valid call recording becomes a diarized transcript in state; CAP-1 and CAP-2 success criteria are the signal.

## Requirements

- CAP-1 (R1): Accept audio by content (magic bytes), not extension; formats WAV, MP3, FLAC, OGG, M4A. (spec CAP-1)
- CAP-1 (R2): Reject files over 50 MB or over 60 minutes. (spec CAP-1)
- CAP-2 (R3): A speaker-labeled transcript in the state contract's `Transcript` format. (spec CAP-2)
- CAP-2 (R4): Byte-identical audio returns the cached transcript without re-running whisper. (spec CAP-2)
- R5: Runs on CPU; model size from `WHISPER_MODEL_SIZE`; no model download in CI. (spec Constraints)

## Done when

1. A non-audio file renamed to an audio extension, a file over 50 MB, and a file over 60 minutes are each rejected with a clear reason.
2. A valid sample call yields transcript segments with speaker labels in the state contract's format.
3. Resubmitting byte-identical audio returns the cached transcript without running whisper.
4. Runs on CPU with `WHISPER_MODEL_SIZE=tiny`; model size is configurable.
5. Both stages run inside the live graph, with tests green.

## Boundaries

Stages 1 and 2 only. Not screening, redaction, or any LLM call.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-1, CAP-2, Constraints
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md, sections Stage mechanics, Whisper on CPU

## Notes

- Decision: speaker labeling is decided by spike 2.2 (pyannote vs. split by channel) before story 2.3 starts (user's decision, 2026-10-11).
- Decision: a rejected file sets status `failed` with a reason; the report and audit trail are still written; the CLI prints `rejected: <reason>` and exits 2 (approved with the breakdown, 2026-10-11).
- Decision: the transcript cache is file-based under `.cache/transcripts/`, keyed by audio SHA-256 plus model size; SQLite stays with Epic 5 (approved with the breakdown, 2026-10-11).
- Decision: accepted formats are WAV, MP3, FLAC, OGG, M4A (approved with the breakdown, 2026-10-11).
- Decision: fixtures are generated with macOS `say` (two-voice stereo plus mono) and committed, so CI needs no real recording (approved with the breakdown, 2026-10-11).
- Decision: Refactor sweep closes the epic (approved with the breakdown, 2026-10-11).
- Waits on epic-platform-baseline because: it needs the state contract and the stage slots.
