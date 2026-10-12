---
title: 'Retry and failure policy'
type: 'feature'
ticket: '3'
created: '2026-10-12'
status: 'built'
baseline_revision: '3362b4e4ce9e850ea11058168406e74b258346eb'
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

**Problem:** Summarization makes one call and fails on the first bad answer or hiccup. A rate limit or a single malformed answer ends the run, and nothing bounds how many calls a stage may make, which the free tiers require (Groq 30 requests/min, Gemini 1,500/day).

**Approach:** One shared helper that every LLM stage calls through: it makes the structured call, validates the answer against the stage's schema, and retries within a fixed budget (user's decision, 2026-10-12). Summarization moves onto it now; QA scoring (4.4) will use it too.

## Boundaries & Constraints

**Always:**
- New `src/call_center/llm_call.py`: `invoke_structured(model, provider, schema, messages)` returns a validated `schema` instance or raises `LLMCallError` carrying the failure kind (invalid output or provider error), the provider, the last error's class name, and the number of attempts.
- Budget: at most 3 calls per stage, so at most 6 per analyzed call once QA scoring is real.
  - Invalid output (parse failure, or the answer fails `schema.model_validate`): one retry. The retry repeats the messages and adds one message listing what was wrong: field paths and pydantic error types only, never the model's text or the transcript.
  - Transient provider errors: up to 2 retries. Transient means rate limit (status 429), timeout, connection failure, or a 5xx server error, recognised for OpenAI, Gemini and Groq exceptions alike (status code or error type). Any other error (auth, bad request) fails at once.
  - Both kinds share the 3-call budget; the helper never makes a 4th call.
- Backoff before a transient retry: 2 s, then 4 s. Sleeping goes through one function that tests replace, so the suite never actually sleeps. The 60 s per-request timeout stays in the clients (4.1/4.2).
- The stage maps `LLMCallError` to status failed with reason "summarization failed: <provider> returned invalid output after <n> attempts" or "summarization failed: <provider> provider error (<ErrorClass>) after <n> attempts", never quoting transcript or model text. On success after more than one attempt, the audit detail adds "after <n> attempts".
- The graph already routes a failed run to report; no change.

**Never:** retries in the clients (they keep `max_retries` off); a retry budget that grows with input; QA scoring (4.4); changing `models.py`, `state.py`, `graph.py`.

## I/O & Edge-Case Matrix

| Scenario | Fake model behaviour | Expected | Calls |
|----------|----------------------|----------|-------|
| First answer valid | valid | summary set; audit "summarized with openai gpt-4o" | 1 |
| One invalid, then valid | invalid, valid | summary set; audit "... after 2 attempts"; the 2nd call has the extra correction message naming the bad field, without the bad text | 2 |
| Invalid twice | invalid, invalid | failed: "summarization failed: openai returned invalid output after 2 attempts"; summary None | 2 |
| Rate limit then valid | 429, valid | summary set; one 2 s backoff requested | 2 |
| Transient three times | timeout, 503, connection error | failed: "... provider error (<class of the last error>) after 3 attempts"; backoffs 2 s and 4 s | 3 |
| Transient then invalid twice | 429, invalid, invalid | failed: invalid output after 3 attempts | 3 |
| Non-transient error | 401 auth error | failed at once: "... provider error (AuthenticationError) after 1 attempts" | 1 |
| Each provider's errors | the real exception classes of openai, google-genai and groq for 429, timeout, 5xx and 401 | classified the same way for all three | — |
| Pipeline | a full run on the fake | failed runs skip QA scoring and reach report with the reason in state and audit | ≤ 3 |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/summarization.py` -- `run` now calls `llm.get_chat_model`, then `model.with_structured_output(**llm.structured_output_args(provider, Summary))` and `invoke`, catching `_INVALID_OUTPUT = (ValidationError, OutputParserException, json.JSONDecodeError)` and any other `Exception`, then `Summary.model_validate` (with `model_dump` for a `BaseModel` answer). Move the call, validation and error mapping into the helper; keep `render_transcript`, `messages`, `_failed`, the config and factory error handling.
- `src/call_center/llm.py` -- `get_chat_model`, `structured_output_args(provider, schema)`, `model_name`, `LLMConfigError`. The helper takes a model the stage already built; no factory change.
- `tests/helpers.py` `FakeChatModel` -- has `output` (one answer or exception), `calls`, `schemas`, `methods`, `settings`; extend it to take a sequence of answers or exceptions, one per call.
- `tests/conftest.py` -- autouse `fake_chat_model`; add an autouse patch of the helper's sleep that records requested delays.
- `tests/unit/test_summarization.py` -- 4.1/4.2 stage tests; the invalid-output and provider-error tests now expect the new reasons ("after N attempts").
- Exception classes for the provider row: `openai` (`RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError`, `AuthenticationError`), `groq` (same names), `google.genai.errors` (`APIError`/`ClientError`/`ServerError` with `code`), plus `httpx` timeout and transport errors. Build them offline in tests; no request is sent.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/llm_call.py` -- the helper, error classification, sleep seam.
- [x] `src/call_center/stages/summarization.py` -- use it.
- [x] `tests/helpers.py`, `tests/conftest.py` -- answer sequences; sleep patch.
- [x] `tests/unit/test_llm_call.py` -- every matrix row at helper level, including the per-provider exception classes; `tests/unit/test_summarization.py` -- the stage reasons and the pipeline row.

**Acceptance Criteria:**
- Given any sequence of fake answers and errors, when a stage runs, then it makes at most 3 calls and either stores a schema-valid result or fails with a reason that holds no transcript or model text (a seeded property test over random sequences).
- Given `uv run pytest`, when it runs, then no test sleeps for real and no request is sent.

## Implementation Notes

- `invoke_structured` returns the validated instance as specified; the stage calls `invoke_structured_counted`, which returns `(instance, attempts)`, so the audit can add "after <n> attempts". `invoke_structured` is a thin wrapper over it.
- Transient classification walks the error's `__cause__` chain (bounded): langchain-google-genai re-raises `ClientError` as `GoogleRateLimitError`/`ChatGoogleGenerativeAIError` and `ServerError` as `GoogleAPIError`, and langchain-openai has its own subclasses. Signals, first match wins: status code (`status_code` on openai/groq `APIStatusError`, `code` on google-genai `APIError`): 429 or 5xx; transport types (`TimeoutError`, `ConnectionError`, `httpx.TimeoutException`/`NetworkError`/`RemoteProtocolError`, openai/groq `APIConnectionError` incl. `APITimeoutError`); langchain `ModelError.is_retryable`.
- Correction message: sorted `path: error_type` lines from the `ValidationError`; path components that are not property names of the schema (an extra key the model invented) are shown as `<unexpected field>`, so no model-chosen text is echoed. Parse failures get a generic line. After an invalid answer the correction stays on later (transient) retries.
- `LLMCallError` is raised `from None`, so provider/model text does not ride along in a traceback; its message holds only provider, kind, class name and attempts.
- A failure in `with_structured_output` itself (no request sent) maps to provider error after 1 attempt.
- Tests: `FakeChatModel.outputs` (one answer/exception per call; a call past the end fails), autouse `backoff_sleeps` fixture patching `llm_call.sleep`. Seeded property tests: 200 seeds at helper level, 100 at stage level.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): medium 1, low 1, false 0, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `FakeChatModel.invoke` overrun | medium | patch | The `AssertionError` for a call past the end was swallowed by the helper's catch-all and reported as a provider error, so an over-budget helper would not fail a test. Now raises `FakeAnswersExhausted` (a `BaseException`); `test_call_past_the_fake_answers_fails_the_test` proves it. |
| 2 | `_verdict` status rule | low | patch | HTTP 408 was non-transient though the plan counts timeouts; now transient with 429 and 5xx, with 408 tests for openai, groq and gemini. |

After patches: `uv run pytest` passed; `HF_HUB_OFFLINE=1 uv run pytest -m slow` passed; ruff clean. OpenAI live check: `uv run pytest -m live` run by the user on 2026-10-12, 1 passed. A slow-suite flake seen once during implementation is logged in `deferred-work.md` with its likely cause (audit timestamps in the card-leak check).

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run pytest -m live` -- expected: still passes on OpenAI (run by the user)
