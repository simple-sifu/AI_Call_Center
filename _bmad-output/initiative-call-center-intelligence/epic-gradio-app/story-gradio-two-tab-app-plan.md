---
title: 'Gradio two-tab app'
type: 'feature'
ticket: '1'
created: '2026-10-12'
status: done
baseline_revision: '8df07b3'
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

**Problem:** The spec success signal requires a browser demo: Analyze Call plus Observability reading Epic 5 persistence.

**Approach:** Add ``gradio_app.py``, ``call-center ui``, and unit tests for markdown formatters and ``run_analyze``.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1567 passed; ruff clean. Launch with ``uv run call-center ui``. Follow-up: WAV ``File`` upload (not ``Audio``) for reliable fixture demos; see README.
