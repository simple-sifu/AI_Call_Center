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

- Open question: diarization tool (spec OQ 1); faster-whisper has none built in.
- Assumption: open with a spike comparing pyannote against a heuristic (unconfirmed).
- Waits on epic-platform-baseline because: it needs the state contract and the stage slots.
