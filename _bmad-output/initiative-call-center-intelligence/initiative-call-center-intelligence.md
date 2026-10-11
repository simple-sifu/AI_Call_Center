---
type: initiative
title: "Every call analyzed, scored consistently, and auditable"
parent: none
covers: [CAP-1, CAP-2, CAP-3, CAP-4, CAP-5, CAP-6, CAP-7, CAP-8, CAP-9, CAP-10]
after: []
assignee: ""
status: in-progress
risk: high
---

# Every call analyzed, scored consistently, and auditable

## Description

A 7-stage LangGraph pipeline turns an uploaded call recording into a diarized, screened, redacted transcript, a structured summary, a deterministic QA score, and a PDF/JSON report with an append-only audit trail, behind a two-tab Gradio app. The spec owns the capabilities, constraints, and non-goals.

## Outcome

A QA reviewer gets a consistent, auditable analysis of any call by uploading it; the spec's success signal is the measure.

## Done when

1. A sample call uploaded in the Gradio app runs all 7 stages and yields a summary, five dimension scores, a Python-computed overall, PDF and JSON reports, and audit entries.
2. The same run succeeds on OpenAI, Gemini, and Groq with only the provider env var changed.
3. 100+ tests pass across unit, integration, and security suites; ruff is clean.
4. The security suite proves no LLM call receives unscreened or unredacted transcript text.
5. It runs on a CPU laptop with `WHISPER_MODEL_SIZE=tiny` on Python 3.11 or 3.12.

## Boundaries

Split by spec capability; one repo, one owner. Not live calls, telephony, auth, a human-review workflow, or throughput targets; see the spec's non-goals. Tracer path: Epic 1's stub graph runs a sample file end to end; each later epic replaces its own stub stage.

- Touch point: OpenAI, Gemini, Groq APIs — consumed via the provider factory; owner: epic-llm-analysis
- Touch point: faster-whisper model weights — downloaded and configured; owner: epic-audio-intake-transcription
- Touch point: LangSmith — tracing configured by env var; owner: epic-platform-baseline

## References

- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md
- constraint — the same spec, section Constraints (stage order, QA weights, Python version, CPU, free-tier limits)
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md
- diagram — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/pipeline-diagram.md

## Notes

- Decision: six epics, split by capability (user's decision, 2026-10-10).
- Assumption: the first demo is CLI + tests in Epic 1, with the UI last (unconfirmed).
- Assumption: the shared pipeline state contract is a hitl story in Epic 1 rather than a bmad-architecture spine (unconfirmed).
- Assumption: "delivered to production" means merged to main, wired into the graph, CI green.
- Decision: each stage lives in its own module; an epic replaces only its own stage, never the graph wiring, so epics 2–4 don't collide.
- Open question: Observability metrics (spec OQ 6) must be settled before Epic 5's inception, since Epic 5 persists what Epic 6 shows.
- Waits on epic-platform-baseline because: every epic replaces a stub in its graph and uses its state contract.
