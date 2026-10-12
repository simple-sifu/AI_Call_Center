---
title: 'PDF report generation'
type: 'feature'
ticket: '3'
created: '2026-10-12'
status: done
baseline_revision: 'a29eac3'
route: 'full'
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

**Problem:** QA reviewers need a downloadable PDF; only JSON exists.

**Approach:** ReportLab `write_pdf` in `reports.py` mirrors JSON facts (status, summary, QA scores, audit). The report stage writes `<stem>.pdf` beside JSON and sets `report_pdf_path` in state.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1549 passed; ruff clean.
