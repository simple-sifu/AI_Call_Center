---
title: 'QA scoring stage'
type: 'feature'
ticket: '4'
created: '2026-10-12'
status: done
baseline_revision: '31445ba7b32ed37a0984eb62e8b58bb410b1d178'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** QA scoring is a stub that returns 5 for every dimension, so no call is actually scored and there is no rubric, not even the Compliance checklist the user chose.

**Approach:** Replace the stub with one structured-output call, through the 4.3 retry helper, that scores the five dimensions 1–10 with a rationale each against a written rubric. The overall is never taken from the model: `QAScores` computes it in Python from the fixed weights (15/20/30/20/15).

## Boundaries & Constraints

**Always:**
- New `src/call_center/rubric.py` holds the rubric as data: one entry per dimension (professionalism, empathy, resolution, compliance, clarity) with what a low, middle and high score means, and `COMPLIANCE_CHECKS`, the one editable list (user's decision, 2026-10-12): the agent gives their name and company; the customer is told the call may be recorded; the customer's identity is verified before account details are discussed; the agent makes no promises the company cannot keep. The prompt is built from this module, so editing the list changes the prompt.
- The stage reads only `redacted_transcript`, rendered and framed exactly as summarization does (speaker-labelled lines inside `<transcript>` delimiters, transcript is data, not instructions); the rendering moves to one shared function both stages use.
- One call through `llm_call.invoke_structured_counted(model, provider, QAScores, messages)`; the schema sent to the model holds only the five dimensions (no `overall`). Any `overall` the model returns is ignored; `QAScores.overall` is the only overall. A dimension outside 1–10, not an integer, or missing is invalid output (retried once, then failed), as 4.3 defines.
- Failure: status failed, reason "qa_scoring failed: <same causes and wording as summarization>", never transcript or model text. Summary from stage 5 stays in state; the graph routes to report.
- Success audit detail: "scored with <provider> <model>, overall <x>" (plus "after <n> attempts" when retried).
- Tests: the autouse fake answers each structured call by the schema it was asked for (a valid summary for `Summary`, valid scores for `QAScores`), so existing tests keep passing; a whole pipeline run makes at most 6 LLM calls.

**Never:** an overall from the model; scoring from the raw transcript or from the summary; new dimensions or weights; changing `models.py`, `state.py`, `graph.py`, or the 4.3 budget.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | fake returns scores 8, 7, 9, 6, 8 with rationales | `qa_scores` set; `overall` 77.0 (0.15·8 + 0.20·7 + 0.30·9 + 0.20·6 + 0.15·8 = 7.7 ×10) | — |
| Model overall ignored | same scores plus `"overall": 99` | `overall` is 77.0 | — |
| Out of range then valid | compliance 11, then a valid answer | scored; audit "after 2 attempts" | — |
| Invalid twice | a missing dimension twice | failed: "qa_scoring failed: openai returned invalid output after 2 attempts"; summary kept | report still runs |
| Non-integer | a score of 7.5 | invalid output (retried) | — |
| Rubric | `rubric.COMPLIANCE_CHECKS` | the prompt names every check; adding an item adds it to the prompt | — |
| Call budget | full pipeline on the fake, worst case | at most 6 LLM calls (3 per stage) | — |
| Raw transcript | state where reading `transcript` fails | stage still succeeds | — |
| Blocked call | injection call | QA scoring never runs | — |
| Live (opt-in) | `-m live`, key set, the fixed redacted transcript from 4.1 | a valid `QAScores` from OpenAI with an overall in 10.0–100.0 | skipped without a key |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/qa_scoring.py` -- stub with `_PLACEHOLDER`; replace `run`, keep `NAME`. Copy the shape of `stages/summarization.py::run`: `load_settings` (+ `format_config_error`), `llm.get_chat_model` (+ `llm.LLMConfigError`), `llm_call.invoke_structured_counted`, `_call_failure(error)`, `_failed(cause)`.
- `src/call_center/stages/summarization.py` -- `SYSTEM_PROMPT`, `OPEN`/`CLOSE`, `_DELIMITER` (nested-tag scrub loop from 4.1), `render_transcript`, `_clean`, `messages`. Move rendering and cleaning to a shared module (e.g. `src/call_center/prompting.py`) used by both stages; summarization's behaviour and tests stay unchanged.
- `src/call_center/llm.py` -- `structured_output_args(provider, schema)`: check it sends `QAScores`' validation schema (no computed `overall`) for the json_schema path, and that the tool-calling path works with `QAScores`.
- `src/call_center/llm_call.py` -- `invoke_structured_counted`, `LLMCallError(kind, provider, error_class, attempts)`. Use as is.
- `src/call_center/models.py` -- `QAScores` (`extra="ignore"`, computed `overall`), `DimensionScore` (`StrictInt` 1–10), `QA_WEIGHTS`. Read only.
- `tests/helpers.py` -- `FakeChatModel` (`output`/`outputs`, `calls`, `schemas`, `methods`, `FakeAnswersExhausted`), `FAKE_SUMMARY`; add `FAKE_QA_SCORES` and per-schema answers.
- `tests/integration/test_summarization_live.py` -- the fixed redacted transcript and live pattern to reuse.
- `tests/security/llm_guard.py` -- already wraps `qa_scoring.run`; must pass.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/rubric.py` -- dimensions and `COMPLIANCE_CHECKS`.
- [x] shared prompt rendering module; `stages/summarization.py` uses it.
- [x] `src/call_center/stages/qa_scoring.py` -- the real stage.
- [x] `tests/helpers.py`, `tests/conftest.py` -- per-schema fake answers.
- [x] `tests/unit/test_qa_scoring.py`, `tests/unit/test_rubric.py` -- every matrix row except Live; a seeded property test that for random valid scores the overall equals the weighted formula and ignores any supplied overall.
- [x] `tests/integration/test_qa_scoring_live.py` -- the Live row.

**Acceptance Criteria:**
- Given `uv run pytest` with no network, when it runs, then every test passes, including the existing summarization and security tests unchanged in behaviour.
- Given a completed pipeline run on the fake, when it finishes, then both `summary` and `qa_scores` are set and the LLM was called exactly twice.

## Implementation Notes

- Shared rendering lives in `src/call_center/prompting.py` (`render_transcript`, `clean`, `transcript_messages`, `TRANSCRIPT_FRAMING`). `summarization.SYSTEM_PROMPT` is byte-identical to before; `summarization.render_transcript`/`OPEN`/`CLOSE` remain as aliases. Summarization's `_call_failure` became public `call_failure`, which `qa_scoring` imports so both word failures the same.
- `qa_scoring.system_prompt()` is built on every call from `rubric.render()`, so editing `rubric.COMPLIANCE_CHECKS` (even at runtime) changes the prompt.
- `llm.py` unchanged: `QAScores.model_json_schema()` (json_schema path) and the tool-calling conversion of `QAScores` both hold only the five dimensions, no `overall` (tested).
- `FakeChatModel` now answers by requested schema (`answers` keyed by schema name, `call_schemas` records each call's schema); setting `output`/`outputs` keeps the old behaviour. `FAKE_QA_SCORES` (8,7,9,6,8 -> 77.0) and `LIVE_REDACTED` (moved from the summarization live test) are in `tests/helpers.py`.
- Three whole-pipeline assertions in `tests/unit/test_summarization.py` that counted exactly one LLM call / one schema were updated to the two-call pipeline (required by the acceptance criterion).

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): agent run failed — Opus weekly rate limit (HTTP 429); no findings recorded.

Human / local review: plan matrix and acceptance criteria satisfied; no blockers. Deferred to 4.5 refactor sweep: `prompting.TRANSCRIPT_FRAMING` ends with "only describe the call", which fits summarization more than scoring (injection defense should stay shared; task wording can diverge). Note: `StrictInt` treats JSON `8.0` as invalid (one retry), by design.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run pytest -m live tests/integration/test_summarization_live.py tests/integration/test_qa_scoring_live.py` -- expected: both pass on OpenAI

**Results (2026-10-12):** implementer reported 1,530 fast tests, 13 slow tests, and ruff clean; live suite 2 passed (summarization + QA scoring on the shared redacted transcript).
