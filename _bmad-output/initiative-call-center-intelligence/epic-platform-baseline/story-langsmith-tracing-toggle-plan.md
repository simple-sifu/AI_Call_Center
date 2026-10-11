---
title: 'LangSmith tracing toggle'
type: 'feature'
ticket: '5'
created: '2026-10-10'
status: done
baseline_revision: '4a51accab22e5a6688cc46e02ea21b2d10de65e4'
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

**Problem:** The tracing settings load from `.env`, but LangSmith reads only `os.environ`, so tracing never turns on from `.env`. A shell variable could also turn it on with no key.

**Approach:** Add `configure_tracing(settings, environ=os.environ) -> bool`. When tracing is requested and an API key is present, it exports the LangSmith variables, plus the project when one is set. Otherwise it forces tracing off, and warns on stderr when tracing was requested without a key. The CLI calls it after loading settings and flushes pending traces before exiting. Without a key a run succeeds and a test asserts tracing is off. With the user's key, the run appears as a trace in LangSmith (hitl).

</frozen-after-approval>

## Implementation Notes

Oneshot: about 40 lines of code and 50 of tests across `config.py`, `cli.py`, and one test file.

- New `src/call_center/tracing.py`:
  - `configure_tracing(settings, environ=None)`: with the flag set and a key present, exports `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` when one is set. Otherwise it sets both `LANGSMITH_TRACING` and `LANGCHAIN_TRACING_V2` to `false`, and warns on stderr when the flag was set without a key.
  - `flush_traces()` wraps langchain-core's `wait_for_all_tracers`.
- `cli.py`: keeps the loaded settings, calls `configure_tracing` before the run, and flushes in `finally` when tracing is on.
- Added `langchain-core` as an explicit dependency, since `tracing.py` imports it directly (it was already installed via langgraph).
- `tests/conftest.py`: the autouse fixture now does `setenv` then `delenv` for every config name, so values the CLI writes to `os.environ` are undone after each test. A bare `delenv` on an absent name records nothing to undo.
- Tests: 5 unit tests in `tests/unit/test_tracing.py`, plus a CLI test asserting a run with no key succeeds with both tracing flags `false`. 55 tests pass; ruff is clean.
- The user's `.env` has the tracing flag, a key, and a project set (checked as booleans only), so a real CLI run sends a trace. That is the hitl check, left to the user.
- Review patch: langsmith reads four flag names, in precedence order `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGCHAIN_TRACING`. The settings alias now lists all four in that order, `TRACING_FLAGS` is derived from it, and both branches write all four. Tests now assert `langsmith.utils.tracing_is_enabled()` (clearing its `lru_cache`) instead of only the strings written. `ENV_VARS` picks up the new names, so the conftest fixture isolates them. 61 tests pass.
- hitl check met (user, 2026-10-10): a real CLI run with the user's key appeared as a trace in LangSmith.

## Review Triage Log

Pass 1 (quick lens): high 0, medium 3, low 1, false 0, maybe-false 0. All four share one root cause (the tracing flag names were incomplete) except #3, a test gap.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `tracing.py` off branch | medium | patch | Confirmed in langsmith 0.14.7 `tracing_is_enabled`/`get_env_var`: `LANGSMITH_TRACING_V2=true` enabled tracing with no key and no warning. Fix: write all four names; settings alias covers them. |
| 2 | `tracing.py` on branch | medium | patch | Same root cause: a leftover `LANGCHAIN_TRACING_V2=false` outranks `LANGSMITH_TRACING`, so the function returned True with tracing off. Fix: write all four names to `true`; settings now uses langsmith's precedence. |
| 3 | tracing tests | medium | patch | Tests asserted only written strings, which is why 1 and 2 passed. Fix: assert langsmith's own `tracing_is_enabled()`, including every flag name and the conflicting-legacy case. |
| 4 | `tests/conftest.py` isolation | low | patch | `LANGSMITH_TRACING_V2` / `LANGCHAIN_TRACING` leaked from the shell. Fixed by the alias change, since `ENV_VARS` derives from the aliases. |
