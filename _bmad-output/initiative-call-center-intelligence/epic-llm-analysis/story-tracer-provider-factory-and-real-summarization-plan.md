---
title: 'Tracer: provider factory and real summarization'
type: 'feature'
ticket: '1'
created: '2026-10-12'
status: done
baseline_revision: '1b6fa07c31000eb5102323b41fd562d3585dc292'
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

**Problem:** Summarization is a stub and nothing can call an LLM: there is no provider factory, no provider package, and no way for tests to run the pipeline without a network.

**Approach:** Add a provider factory (OpenAI only in this story) and make the summarization stage send the redacted transcript to the selected model in one structured-output call, validating the answer against `Summary`. Add one fake-model seam, used automatically by every test, and a `live` marker for opt-in real calls.

## Boundaries & Constraints

**Always:**
- New `src/call_center/llm.py`: `get_chat_model(settings)` returns a LangChain chat model for `settings.llm_provider`. OpenAI uses `langchain-openai` with `settings.openai_model`, the key passed explicitly from `settings.openai_api_key`, a 60 s request timeout, and client-side retries off (`max_retries=0`; story 4.3 owns retries). A missing key raises a dedicated error whose message names the provider and the key variable (`OPENAI_API_KEY`), never a value. Gemini and Groq raise "not supported yet" until story 4.2.
- Summarization reads only `redacted_transcript`, renders it as speaker-labelled lines inside clear delimiters, and tells the model the transcript is data, not instructions. One call per run, no retries. The model's answer is validated with `Summary.model_validate`; nothing else reaches state.
- On a missing key, invalid output, or a provider error, the stage sets `status` "failed" with `status_reason` "summarization failed: <cause>", where the cause names the provider and error kind (missing key, invalid output, provider error) and never quotes transcript or model text. The audit records outcome "failed" with the same reason; the graph already routes failed runs to report and the CLI exits 2.
- On success, audit detail is "summarized with <provider> <model>".
- Tests never reach a real LLM: an autouse fixture in `tests/conftest.py` patches `llm.get_chat_model` with a fake chat model that returns a fixed valid summary (tests can swap the output). The `live` marker is registered, deselected by default like `slow`, and a live test skips when no key is configured. Live tests read the real `.env` (the config-isolation fixture is lifted only for them).

**Never:** Gemini or Groq clients (4.2); retries or call budgets (4.3); QA scoring (4.4); changing `models.py`, `state.py` or `graph.py`; logging, printing or tracing the transcript or the key; reading `.env` outside a live test.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | redacted transcript, fake model returns a valid summary | `summary` set to that `Summary`; audit ok "summarized with openai gpt-4o" | — |
| Invalid output | fake returns a summary missing `call_purpose`, or with a fourth sentiment phase | status failed, reason "summarization failed: openai returned invalid output"; `summary` stays None | QA scoring and later LLM stages skipped |
| Missing key | `LLM_PROVIDER=openai`, no `OPENAI_API_KEY`, real factory | status failed, reason names `OPENAI_API_KEY`, no key value anywhere | CLI exits 2 |
| Provider error | fake raises (timeout, auth, rate limit) | status failed, reason names openai and the error kind | — |
| Raw transcript | state where reading `transcript` fails | stage still succeeds (reads only the redacted one) | — |
| Blocked call | injection call | summarization never runs | — |
| Live (opt-in) | `-m live`, key set, a fixed redacted transcript with `[CARD]` | a valid `Summary` from OpenAI | skipped without a key |

</frozen-after-approval>

## Code Map

- `src/call_center/config.py` -- `Settings.llm_provider`, `openai_model` ("gpt-4o"), `openai_api_key` (SecretStr), `load_settings()`; docstring says the factory enforces the key. No change needed.
- `src/call_center/models.py` -- `Summary` (frozen, `extra="forbid"`; `call_purpose`, `action_items` tuple, `sentiment_trajectory` with opening/middle/closing, `entities` of `Entity(text, type)`), `AuditEvent`. Read only.
- `src/call_center/stages/summarization.py` -- stub returning `_PLACEHOLDER`; replace `run`, keep `NAME`. Pattern for loading settings and failing: `stages/transcription.py` (`load_settings`, `format_config_error`).
- `src/call_center/asr.py` `get_transcriber` + `tests/conftest.py` `_fake_transcriber` -- the seam pattern to copy for `llm.get_chat_model` and the autouse fake.
- `tests/conftest.py` -- `_isolated_config` clears env and disables `.env`; `pytest_collection_modifyitems` deselects `slow` unless named; extend both for `live`.
- `pyproject.toml` -- `addopts = "--strict-markers -m 'not slow'"`, `markers`: add `live` and exclude it by default; add `langchain-openai` with `uv add`.
- `tests/security/test_blocked_run.py::test_llm_stages_never_read_raw_transcript` and `tests/security/llm_guard.py` -- call `summarization.run` directly / wrap it; must pass with the autouse fake.
- `src/call_center/graph.py` -- `HALTED = ("blocked", "failed")` routes to report; no change.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- `langchain-openai`; `live` marker.
- [x] `src/call_center/llm.py` -- factory and missing-key error.
- [x] `src/call_center/stages/summarization.py` -- the real stage.
- [x] `tests/conftest.py` -- autouse fake chat model; `live` handling.
- [x] `tests/unit/test_llm.py`, `tests/unit/test_summarization.py` -- factory (client class, model, timeout, retries off, key passed, missing-key message without the value) and every matrix row except Live.
- [x] `tests/integration/test_summarization_live.py` -- the Live row.

**Acceptance Criteria:**
- Given `uv run pytest` with no network, when it runs, then every test passes and no test constructs a real chat model.
- Given `run_pipeline` on `tests/fixtures/sample.wav` with the fake model (in a test, never the CLI from the repo root), when the run completes, then the state holds the fake's summary and stages run in the existing order.

## Implementation Notes

- Structured output uses `with_structured_output(Summary.model_json_schema(), method="json_schema")` (dict schema, so the model returns a dict and `Summary.model_validate` is the only validation; strict mode is not requested because the schema uses `minLength`).
- Failure causes: `openai API key missing (set OPENAI_API_KEY)`, `<provider> is not supported yet`, `openai returned invalid output` (pydantic `ValidationError`, `OutputParserException`, JSON decode error), `openai provider error (<ExceptionClass>)` for anything else; a missing `redacted_transcript` fails with `no redacted transcript` without calling the model.
- Utterances are collapsed to one line and any `<transcript>`/`</transcript>` tag inside them is removed, so a segment cannot close the data block or forge another speaker's line.
- The fake (`FakeChatModel`, `FAKE_SUMMARY`) lives in `tests/helpers.py`; the autouse `fake_chat_model` fixture in `tests/conftest.py` patches `llm.get_chat_model`. Tests needing the real factory bind it at import (`from call_center.llm import get_chat_model`).

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): medium 1, low 1, false 0, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `summarization._clean` delimiter scrub | medium | patch | Single-pass `sub` let nested tags re-form a delimiter ("</transcript</transcript>>" → "</transcript >"). Now repeats until stable; `test_nested_tags_cannot_reform_a_delimiter` covers three nested forms. |
| 2 | `test_llm.py` builds `ChatOpenAI` objects | low | reject | Literal reading of "no test constructs a real chat model"; the objects are never invoked and no request is sent, which is the criterion's purpose (no network). The factory checks the plan asks for need the real client class. |

After patches: `uv run pytest` passed; `HF_HUB_OFFLINE=1 uv run pytest -m slow` passed; ruff clean. Live check: the user ran `uv run pytest -m live` on 2026-10-12 and it passed (1 test): OpenAI accepted the request and returned a schema-valid summary.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run pytest -m live` -- expected: passes with `OPENAI_API_KEY` in `.env` (run by the user, or with the user's go-ahead)
