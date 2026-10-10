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
3. Each stage has an audit entry, and the application offers no path to update or delete audit entries.
4. Stage 7 runs inside the live graph, with tests green.

## Boundaries

Stage 7 and the persistence layer. Not the UI.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-7
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md

## Notes

- Open question: the Observability metrics (spec OQ 6) must be settled before this epic's inception, since this epic persists them.
- Open question: whether raw or unredacted text may be stored (spec OQ 4).
- Waits on epic-llm-analysis because: reports render its summary and scores.
