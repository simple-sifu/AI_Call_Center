---
title: 'Refactor sweep'
type: 'refactor'
ticket: '5'
created: '2026-10-12'
status: done
baseline_revision: '30b4b84'
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

**Problem:** Epic 4 left one shared `TRANSCRIPT_FRAMING` string whose closing line says "only describe the call". That fits summarization but reads wrong in the QA scoring system prompt (the model scores and rationales, it does not summarize).

**Approach:** Split the injection-defense framing into a shared prefix plus stage-specific one-line tails. Summarization keeps byte-identical `SYSTEM_PROMPT`; QA scoring uses scoring-appropriate wording. No change to delimiter rendering, retry policy, rubric, or models.

**Never:** behaviour changes outside prompt wording; float `8.0` score coercion (deferred by design in 4.4).

</frozen-after-approval>

## Implementation Notes

- `prompting.py`: shared prefix; `TRANSCRIPT_FRAMING_SUMMARIZATION` and `TRANSCRIPT_FRAMING_SCORING`; `TRANSCRIPT_FRAMING` aliases summarization for compatibility.
- `summarization.py`: uses `TRANSCRIPT_FRAMING_SUMMARIZATION` (same assembled prompt as before).
- `qa_scoring.py`: uses `TRANSCRIPT_FRAMING_SCORING`.
- `tests/unit/test_prompting.py`: alias, summarization still uses "describe the call", scoring uses the scoring tail.

## Review Triage Log

Pass 1 (quick lens): not run (deferred to PR).

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean

**Results (2026-10-12):** 1533 passed; slow 13 passed; ruff clean.
