---
type: epic
title: "Reports and audit trail"
parent: initiative-call-center-intelligence
covers: [CAP-7]
after: []
assignee: ""
risk: medium
---

# Reports and audit trail

## Description

Real stage 7: PDF and JSON reports per call, a SQLite record of each call, and an append-only audit log of every stage.

## Outcome

Every analyzed call leaves a downloadable report and a provable audit trail; CAP-7's success criterion is the signal.

## Done when

1. After a run, a PDF and a JSON report exist for the call, and they agree with the state.
2. The call's row is in SQLite, with whatever the Observability tab needs persisted.
3. Each stage that ran has an audit entry (a blocked or failed call is reported too), and the application offers no path to update or delete audit entries.
4. Stage 7 runs inside the live graph, with tests green.

## Boundaries

Stage 7 and the persistence layer. Not the UI.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-7
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md

## Notes

- Decision: persistence stores **redacted transcript and analysis results only**, never the raw transcript (user inception Epic 5, 2026-10-12; resolves spec OQ 4 for the DB/reports path). The local transcript cache may still hold raw text, as already decided.
- Decision: Observability persistence (spec OQ 6) for Epic 5 is **provider, status, overall, analyzed_at, and per-stage audit outcomes**; token/cost/latency columns are nullable until LangSmith or the LLM layer exposes them to the report stage (2026-10-12). Epic 6 reads these columns; it does not redefine them.
- Waits on epic-llm-analysis because: reports render its summary and scores.
- Breakdown: `epic-reports-audit/tickets.toml` — JSON tracer (5.1), SQLite audit (5.2), PDF (5.3), observability columns (5.4), refactor (5.5), e2e suite (5.6).
