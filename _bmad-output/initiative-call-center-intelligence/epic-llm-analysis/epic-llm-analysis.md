---
type: epic
title: "LLM analysis and provider switching"
parent: initiative-call-center-intelligence
covers: [CAP-8, CAP-5, CAP-6]
after: []
assignee: ""
risk: high
---

# LLM analysis and provider switching

## Description

The multi-provider LLM factory, plus real stages 5 and 6: a schema-validated summary, and QA scoring whose overall is always recomputed in Python.

## Outcome

Any safe transcript gets a structured summary and a drift-proof QA score on whichever provider is configured; CAP-5, CAP-6, and CAP-8 success criteria are the signal.

## Done when

1. Changing only the provider env var runs the same pipeline on OpenAI, Gemini, and Groq, with no code edits.
2. The summary validates against its schema; schema-invalid LLM output is rejected or retried, never passed on.
3. The overall score equals the fixed weighted sum (15/20/30/20/15) computed in Python; an LLM-supplied overall is ignored.
4. LLM calls per analyzed call stay within the Gemini and Groq free-tier limits.
5. Both stages run inside the live graph after the safety stages, with tests green.

## Boundaries

The provider factory and stages 5 and 6. Not report rendering or persistence.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-5, CAP-6, CAP-8, Constraints (weights, free tiers)
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md, section LLM providers

## Notes

- Open question: which disclosures the Compliance dimension checks (spec OQ 3).
- Decision: each dimension is scored 1–10 with a rationale; overall = round(weighted mean × 10, 1), computed by `QAScores` (user's decision, 2026-10-10, story 1.1).
- Open question: retry, timeout, and malformed-output handling per provider (spec OQ 7).
- Waits on epic-transcript-safety because: no LLM may see a transcript before screening and redaction.
