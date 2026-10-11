---
title: 'CI'
type: 'chore'
ticket: '4'
created: '2026-10-10'
status: done
baseline_revision: '987f8826cf9e82962f12d8e94dd3ca4157fc9267'
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

**Problem:** Nothing checks lint and tests automatically, so PRs merge on trust and Python 3.11 support is never exercised.

**Approach:** Add one GitHub Actions workflow that runs `ruff check`, `ruff format --check`, and `pytest` on Python 3.11 and 3.12 for pushes to main and for pull requests, using uv with the committed lockfile. It needs no API keys and downloads no models.

</frozen-after-approval>

## Implementation Notes

Oneshot: a single new workflow file of about 30 lines, with no code changes.

- Added `.github/workflows/ci.yml`: triggers on push to main and on pull requests; read-only `contents` permission; a matrix over 3.11 and 3.12 with `fail-fast: false`; `astral-sh/setup-uv@v6` with `python-version` (overrides `.python-version`); then `uv sync --locked`, ruff check, ruff format --check, pytest.
- Verified locally on 3.11.15 in a separate environment: `uv sync --locked` succeeds, 37 tests pass, ruff is clean.

## Verification

**Commands:**
- `UV_PYTHON=3.11 UV_PROJECT_ENVIRONMENT=<tmp> uv sync --locked && uv run pytest` -- expected: passes on 3.11 locally
- Workflow run on the PR -- expected: both matrix jobs green

## Review Triage Log

Pass 1 (quick lens): no findings.
