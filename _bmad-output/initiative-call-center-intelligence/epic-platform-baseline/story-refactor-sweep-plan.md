---
title: 'Refactor sweep'
type: 'refactor'
ticket: '6'
created: '2026-10-10'
status: 'built'
baseline_revision: '3cc50bfa8230f8c834f64538871624c8d99bf593'
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

**Problem:** Epic 1 left small inconsistencies. `graph.run_pipeline` repeats every state field to build the initial state, the edge loop uses `zip(..., strict=False)` where `pairwise` says it directly, and two stubs pass lists where the contract uses tuples.

**Approach:** Cleanup only, with no behavior change. Move the initial state into `state.initial_state(path)`, use `itertools.pairwise` in `build_graph`, and make the placeholders use tuples. Scope comes from the epic's plans: `deferred-work.md` is empty, and the remaining rejected findings are either a behavior change (the `--out` traceback, proposed as a backlog bug) or unreachable (the START edge).

</frozen-after-approval>

## Implementation Notes

Oneshot: about 20 lines in `state.py`, `graph.py`, and two stubs; existing tests must pass unchanged.

- `state.py`: added `initial_state(source_file)`; `graph.run_pipeline` now calls it.
- `graph.py`: `itertools.pairwise(STAGES)` replaces `zip(STAGES, STAGES[1:], strict=False)`.
- `transcription.py` and `summarization.py` placeholders use tuples, matching the contract.
- 61 tests pass on 3.12 and 3.11 with no test edits; ruff is clean.
- Proposed separately as a backlog bug, not swept: `call-center analyze --out <existing file>` raises an uncaught `FileExistsError` traceback (story 1.2 review, finding 4).

## Review Triage Log

Pass 1 (quick lens): no findings.
