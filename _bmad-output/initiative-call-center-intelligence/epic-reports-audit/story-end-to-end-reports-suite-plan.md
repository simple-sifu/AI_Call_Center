---
title: 'End-to-end reports suite'
type: 'feature'
ticket: '6'
created: '2026-10-12'
status: done
baseline_revision: '867e6fa'
route: 'oneshot'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 5 lacked integration proof that JSON, PDF, SQLite, and observability rows stay aligned for every terminal status.

**Approach:** Add ``tests/integration/test_reports_e2e.py`` for completed (fake ASR + fake LLM), blocked (injection ASR), and failed (intake rejection) paths.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1560 passed; ``tests/integration/test_reports_e2e.py`` (3 cases) offline.
