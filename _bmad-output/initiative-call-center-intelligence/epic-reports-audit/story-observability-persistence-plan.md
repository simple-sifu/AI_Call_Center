---
title: 'Observability persistence fields'
type: 'feature'
ticket: '4'
created: '2026-10-12'
status: done
baseline_revision: '9b5bfe8'
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

**Problem:** Epic 6 needs queryable metrics; the calls table lacked stage outcomes, PDF path, and reserved nullable token/latency columns.

**Approach:** Extend ``CallRow`` with ``stage_outcomes_json``, ``report_pdf_path``, and nullable LLM/pipeline metrics; add ``observability.list_observability_records`` for read-only access.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1554 passed; ruff clean.
