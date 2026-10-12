---
title: 'Refactor sweep'
type: 'chore'
ticket: '5'
created: '2026-10-12'
status: done
baseline_revision: '867e6fa'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Report stage duplicated output-dir resolution, artifact naming, and finalized ``CallReport`` assembly; persistence tests duplicated a large fixture builder.

**Approach:** Centralize ``report_output_dir``, ``artifact_paths``, and ``finalized_report`` in ``reports.py``; share ``sample_persist_report`` in ``tests/helpers.py``.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1560 passed; ruff clean; report stage behavior unchanged.
