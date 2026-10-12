---
title: 'Gemini and Groq providers'
type: 'feature'
ticket: '2'
created: '2026-10-12'
status: 'built'
baseline_revision: 'ca42ed737df6ce0685b9d2f59db0d37cc9178760'
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

**Problem:** The factory only builds OpenAI; `LLM_PROVIDER=gemini` or `groq` fails with "not supported yet", so the graded one-variable provider switch does not work.

**Approach:** Add Gemini (`langchain-google-genai`) and Groq (`langchain-groq`) to `llm.get_chat_model`, built the same way as OpenAI, and let the factory say which structured-output method each provider uses, so summarization works unchanged on all three. Verified offline only: only an OpenAI key is available (user's decision, 2026-10-12).

## Boundaries & Constraints

**Always:**
- Gemini: `ChatGoogleGenerativeAI` with `settings.gemini_model`, the key passed explicitly from `settings.gemini_api_key` (read from `GEMINI_API_KEY` or `GOOGLE_API_KEY`), 60 s timeout, client retries off. Groq: `ChatGroq` with `settings.groq_model`, the key from `settings.groq_api_key`, 60 s timeout, client retries off. Same as OpenAI in 4.1.
- A missing key raises `MissingAPIKeyError`, whose message names the provider and its variables (`GEMINI_API_KEY / GOOGLE_API_KEY`, `GROQ_API_KEY`), never a value; the stage fails the run exactly as in 4.1.
- Structured output per provider, chosen by the factory (one place): OpenAI keeps 4.1's `json_schema` call with `Summary`'s JSON schema (proven live). Gemini and Groq use tool calling with the `Summary` class, because those providers do not reliably accept that JSON schema; the stage still validates every answer with `Summary.model_validate`.
- Changing only `LLM_PROVIDER` (plus that provider's key) switches provider; no other setting or code change. Audit reads "summarized with <provider> <model>".
- `ProviderNotSupportedError` goes away, since all three `LLMProvider` values are built.

**Never:** live calls to Gemini or Groq; retries (4.3); QA scoring (4.4); changing `config.py` defaults, `models.py`, `state.py` or `graph.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Gemini client | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=k` | a `ChatGoogleGenerativeAI` for `gemini-2.0-flash`, key k, timeout 60, retries 0 | — |
| Google key name | only `GOOGLE_API_KEY=k` | same client with key k | — |
| Groq client | `LLM_PROVIDER=groq`, `GROQ_API_KEY=k` | a `ChatGroq` for `llama-3.3-70b-versatile`, key k, timeout 60, retries 0 | — |
| Model override | `GEMINI_MODEL=x` / `GROQ_MODEL=y` | that model id | — |
| Missing key | provider selected, no key | run failed, reason names the provider and its key variables; no value anywhere | CLI exits 2 |
| Other provider's key only | `LLM_PROVIDER=groq`, only `OPENAI_API_KEY` set | missing-key failure naming `GROQ_API_KEY` (no fallback to another provider or key) | — |
| Switch by one variable | the same pipeline run with only `LLM_PROVIDER` changed over openai, gemini, groq (fake chat model) | completed each time, audit names that provider and model, the fake saw the structured-output method for that provider | — |

</frozen-after-approval>

## Code Map

- `src/call_center/llm.py` -- `get_chat_model`, `_openai` (pattern to copy: key check, lazy import, `timeout=REQUEST_TIMEOUT_S`, `max_retries=0`), `MissingAPIKeyError(provider, key_field)` (uses `config.env_names`), `ProviderNotSupportedError` (remove), `model_name`. Add `_gemini`, `_groq`, and a function the stage calls to get the structured-output arguments for the selected provider. Update the module docstring.
- `src/call_center/stages/summarization.py` -- `run` calls `model.with_structured_output(Summary.model_json_schema(), method="json_schema")`; replace that with the factory's per-provider arguments. `_INVALID_OUTPUT` and the `Summary.model_validate` step stay; a tool-calling answer may arrive as a `Summary` instance (already handled by `model_dump`).
- `src/call_center/config.py` -- `gemini_model`, `groq_model`, `gemini_api_key` (aliases `GEMINI_API_KEY`, `GOOGLE_API_KEY`), `groq_api_key`. Read only.
- `tests/helpers.py` `FakeChatModel` and `tests/conftest.py` `fake_chat_model` -- the autouse fake from 4.1; extend it to record the structured-output arguments it was given, if it does not already.
- `tests/unit/test_llm.py` -- 4.1's OpenAI factory tests (they build real client objects and never send a request); add the Gemini and Groq ones beside them, and delete the "not supported yet" tests.
- `pyproject.toml`, `uv.lock` -- `uv add langchain-google-genai langchain-groq`; versions must work with the locked `langchain-core`.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- the two packages.
- [x] `src/call_center/llm.py` -- Gemini, Groq, per-provider structured-output arguments.
- [x] `src/call_center/stages/summarization.py` -- use them.
- [x] `tests/unit/test_llm.py`, `tests/unit/test_summarization.py` -- every matrix row.

**Acceptance Criteria:**
- Given `uv run pytest` with no network, when it runs, then every test passes and no request is sent to any provider.
- Given `LLM_PROVIDER=openai`, when the existing live test runs, then it still passes (the OpenAI path is unchanged).

## Implementation Notes

- Locked: `langchain-google-genai` 4.4.1, `langchain-groq` 1.1.3; `langchain-core` stays 1.6.9.
- `llm.structured_output_args(provider, schema)` returns the `with_structured_output` kwargs: OpenAI `{schema: Summary JSON schema, method: "json_schema"}`; Gemini/Groq `{schema: Summary, method: "function_calling"}`. Factory dispatch is a provider-to-builder dict.
- `FakeChatModel` now records `methods` beside `schemas`.
- Review fixes: Gemini uses `max_retries=1` (langchain-google-genai's documented "one attempt"; 0 means the Google default of 5 retries). Gemini is pinned with `vertexai=False`, and `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_GENAI_USE_ENTERPRISE` are hidden while it is built, because google-genai's `Client` reads them itself even when langchain is pinned. The `langchain_google_genai._function_utils` logger is set to ERROR to stop its per-call schema warnings on stderr.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): medium 3, low 1, false 0, maybe-false 0. Verified against the installed library source (no request sent).

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `_gemini` retries | medium | patch | langchain-google-genai documents `max_retries=0` as "Google default (5 retries)"; 0 worked only via a google-genai 2.29.0 quirk. Now `max_retries=1` (documented as no retries); test asserts the built request makes exactly one attempt. |
| 2 | `_gemini` backend | medium | patch | `GOOGLE_GENAI_USE_VERTEXAI` (and `GOOGLE_GENAI_USE_ENTERPRISE`) switch to Vertex AI, read by google-genai itself even with `vertexai=False`. Pinned `vertexai=False`, the client is built with those variables hidden, tests clear them, docstring corrected. |
| 3 | Gemini schema warnings on stderr | medium | patch | `$defs`/`additionalProperties` warnings printed on every Gemini run. That logger is set to ERROR; test asserts empty stderr. |
| 4 | CLI missing-key test Groq only | low | patch | Now parametrized over gemini and groq. |

After patches: `uv run pytest` 999 passed; `HF_HUB_OFFLINE=1 uv run pytest -m slow` 13 passed; ruff clean. OpenAI live check: the user reported running `uv run pytest -m live` as done on 2026-10-12 (output not shown in the session). Gemini and Groq are unverified against the real services (no keys).

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run pytest -m live` -- expected: passes on OpenAI (run by the user)
