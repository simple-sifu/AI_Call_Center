---
title: 'Tracer: JSON report from pipeline state'
type: 'feature'
ticket: '1'
created: '2026-10-12'
status: done
baseline_revision: 'c2cce12'
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

**Problem:** The CLI writes a stub JSON report (`status: stub`, three fields). The report stage is a stub and does not reflect summary, scores, audit, or real run status.

**Approach:** Add `CallReport` and `reports.build_report` / `write_json`. The report stage writes `<stem>.json` under `report_output_dir` (from `run_pipeline(..., report_output_dir=)` or `REPORT_OUTPUT_DIR`, default `reports`). JSON holds real status (``running`` becomes ``completed`` in the file), full audit including the report stage, redacted transcript and analysis when present, never the raw transcript. CLI prints the written path and keeps exit codes for failed/blocked runs.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** `uv run pytest` 1542 passed; ruff clean.
