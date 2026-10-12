---
title: 'SQLite persistence and append-only audit'
type: 'feature'
ticket: '2'
created: '2026-10-12'
status: built
baseline_revision: 'edd9f8d'
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

**Problem:** JSON reports exist on disk but nothing is queryable for Epic 6; there is no durable audit log.

**Approach:** SQLAlchemy + SQLite (`DATABASE_URL`, default `sqlite:///call_center.db`): insert one `calls` row and one `audit_events` row per audit entry when the report stage finishes. Store redacted transcript and analysis as JSON text only. Public persistence API is insert/read-for-tests only — no update or delete for audit rows.

</frozen-after-approval>

## Verification

**Results (2026-10-12):** 1547 passed; ruff clean.
