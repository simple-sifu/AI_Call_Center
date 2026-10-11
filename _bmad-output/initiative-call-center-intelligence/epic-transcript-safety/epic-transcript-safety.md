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

## Requirements

- CAP-3 (R1): A catalogue of 22 injection patterns detects adversarial transcript text; a match blocks the call with a reason naming the pattern ids and categories, never quoting the transcript. (spec CAP-3)
- CAP-3 (R2): A blocked call never reaches PII redaction or any LLM stage. (spec CAP-3, Constraints)
- CAP-4 (R3): SSN, credit card (Luhn-checked), email, and phone values, written as digits or as spoken number words, are replaced by typed placeholders in the text passed on; clean text is unchanged. (spec CAP-4)
- R4: The security suite proves the stage order, R2, and R3 end to end. (spec Constraints)

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

- Open question: what the 22 patterns are (spec OQ 2); story 3.2 drafts them for the user's approval.
- Decision: the 22 patterns are drafted in story 3.2 across instruction override, role reassignment, system-prompt extraction, score manipulation, and jailbreak framing, and the user approves the catalogue (user's decision, 2026-10-11).
- Decision: PII scope is the spec's four types, plus spoken-number normalization (story 3.4); dates of birth, account numbers, names, and addresses are out of scope for this epic (user's decision, 2026-10-11).
- Decision: redactions use typed placeholders `[SSN]`, `[CARD]`, `[EMAIL]`, `[PHONE]`; the audit records counts by type, never values (user's decision, 2026-10-11).
- Decision: a block reason names pattern ids and categories and never quotes transcript text (user's decision, 2026-10-11).
- Decision: Refactor sweep closes the epic (approved with the breakdown, 2026-10-11).
- Decision: a match blocks the call rather than flagging it; the graph skips to the report stage (user's decision, 2026-10-10, story 1.1).
- Open question: whether unredacted text may be stored in the database (spec OQ 4) belongs to Epic 5; the local transcript cache was decided in story 2.4.
- Waits on epic-platform-baseline because: it needs the transcript segment format.
