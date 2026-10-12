---
title: 'End-to-end analysis suite'
type: 'feature'
ticket: '6'
created: '2026-10-12'
status: done
baseline_revision: 'd4ff759'
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

**Problem:** CAP-5, CAP-6, and CAP-8 are proven in unit tests and scattered integration checks, but Epic 4 has no single suite that runs the full graph with provider switching, the LLM guard on both stages, and a blocked call that never reaches them.

**Approach:** Add integration tests that parametrize `LLM_PROVIDER` over openai, gemini, and groq on a fake ASR benign call; assert summary, scores, two structured calls, and `llm_guard.assert_redacted_only`. Add one blocked-path test with `assert_not_run`. Add one opt-in live test that runs summarization then QA scoring on the shared redacted transcript when `OPENAI_API_KEY` is set.

**Never:** network in the default suite; changing stage behaviour; replacing the existing per-stage live modules (they stay; the live test complements them).

</frozen-after-approval>

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior |
|----------|--------------|---------------------------|
| Per provider | fake ASR benign mono call, `LLM_PROVIDER` each of openai/gemini/groq | `completed`; summary and `qa_scores`; guard passes; exactly two LLM schemas Summary then QAScores |
| Blocked | fake ASR injection text | `blocked`; guard: no LLM stage ran |
| Live | `-m live`, OpenAI key, `LIVE_REDACTED` | both stages succeed in one test |

## Code Map

- `tests/integration/test_llm_analysis_e2e.py` -- offline Epic 4.6 suite.
- `tests/integration/test_llm_analysis_live.py` -- opt-in OpenAI check for both LLM stages.
- Reuses `tests/security/llm_guard.py`, `tests/helpers.py` (`FakeTranscriber`, `LIVE_REDACTED`, fakes), `tests/conftest.py` fake chat model.

## Tasks & Acceptance

**Execution:**
- [x] `tests/integration/test_llm_analysis_e2e.py`
- [x] `tests/integration/test_llm_analysis_live.py`

**Acceptance Criteria:**
- Given `uv run pytest`, when it runs, then the new offline tests pass for all three providers.
- Given `uv run pytest -m live` with a key, when it runs, then the new live test and the existing summarization/QA live tests pass.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run pytest -m live tests/integration/test_llm_analysis_live.py tests/integration/test_summarization_live.py tests/integration/test_qa_scoring_live.py` -- expected: pass with key (user)

**Results (2026-10-12):** 1537 passed offline; slow 13 passed; live 3 passed; ruff clean.
