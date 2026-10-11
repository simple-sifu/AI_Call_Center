---
type: epic
title: "Transcript safety"
parent: initiative-call-center-intelligence
covers: [CAP-3, CAP-4]
after: []
assignee: ""
risk: high
---

# Transcript safety

## Description

Real stages 3 and 4: block adversarial transcripts with the injection patterns, and redact PII, so no LLM ever sees unscreened or unredacted text.

## Outcome

The pipeline is safe to hand to an LLM; the security suite proving CAP-3 and CAP-4 is the signal.

## Done when

1. A transcript matching any of the 22 injection patterns blocks the call: the remaining analysis stages are skipped, a test proves the LLM client is never invoked, and the report stage still records the call with its reason.
2. SSN, credit card, email, and phone values seeded in a transcript are absent from the text passed on.
3. Clean transcripts pass through unchanged apart from redactions.
4. Both stages run inside the live graph, ahead of any LLM stage, with the security suite green.

## Boundaries

Stages 3 and 4 only. Built and tested on fixture transcripts, so it runs in parallel with Epic 2.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-3, CAP-4, Constraints (stage order)

## Notes

- Open question: what the 22 patterns are (spec OQ 2).
- Decision: a match blocks the call rather than flagging it; the graph skips to the report stage (user's decision, 2026-10-10, story 1.1).
- Open question: PII scope beyond the four types, and whether raw text may be stored (spec OQ 4).
- Waits on epic-platform-baseline because: it needs the transcript segment format.
