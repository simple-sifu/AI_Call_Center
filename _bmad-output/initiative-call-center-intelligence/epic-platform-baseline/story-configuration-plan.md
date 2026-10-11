---
title: 'Configuration'
type: 'feature'
ticket: '3'
created: '2026-10-10'
status: 'built'
baseline_revision: '7e4603f0854b88ed53ebca41dd7c5de15129ab3d'
route: 'full'
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

**Problem:** Nothing reads configuration, so the provider choice, API keys, whisper model size, and tracing settings that later epics need have no single home, and bad values would surface deep inside a run.

**Approach:** Add a `pydantic-settings` model that loads from the environment and `.env`, accepts the variable names already in the user's `.env`, and validates values up front. Add `.env.example` listing every variable. Load settings at CLI start, so invalid config fails fast with a clear message.

## Boundaries & Constraints

**Always:**
- `LLM_PROVIDER` is one of `openai`, `gemini`, `groq`; default `openai` (spec: recommended default).
- `WHISPER_MODEL_SIZE` is one of `tiny`, `base`, `small`, `medium`, `large-v3`; default `tiny` (spec: CPU development).
- Per-provider model names with spec defaults: `OPENAI_MODEL` = `gpt-4o`, `GEMINI_MODEL` = `gemini-2.0-flash`, `GROQ_MODEL` = `llama-3.3-70b-versatile`.
- API keys are optional at load time: stubs need none, and the Epic 4 factory enforces the selected provider's key. Keys are `SecretStr`, so they never appear in repr, logs, or error messages.
- Accepted names: `OPENAI_API_KEY`; `GEMINI_API_KEY` or `GOOGLE_API_KEY`; `GROQ_API_KEY`. For tracing, `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` or the legacy `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT`.
- Unknown variables in `.env` (e.g. `SERPAPI_API_KEY`) are ignored.
- Tests never read the real `.env` or depend on the developer's shell environment.

**Never:** turning tracing on (story 1.5); a provider factory or key enforcement (Epic 4); touching `models.py`, `state.py`, or the stage modules; committing `.env`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Defaults | no env vars, no `.env` | provider `openai`, whisper `tiny`, spec model defaults, keys `None`, tracing off | No error expected |
| Env override | `LLM_PROVIDER=groq`, `WHISPER_MODEL_SIZE=small` | values applied | No error expected |
| Legacy tracing names | `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY=k` | tracing flag true, key set | No error expected |
| Invalid provider | `LLM_PROVIDER=claude` | CLI exits 2, nothing written | stderr starts `invalid configuration:`, names `LLM_PROVIDER`, lists allowed values |
| Invalid whisper size | `WHISPER_MODEL_SIZE=huge` | CLI exits 2 | same message format, names `WHISPER_MODEL_SIZE` |
| Secret hygiene | `OPENAI_API_KEY=sk-test-123` | `repr(settings)` and any error text never contain `sk-test-123` | No error |

</frozen-after-approval>

## Code Map

- `src/call_center/cli.py` -- `main(argv)`: parses args, validates the input file, runs the pipeline. Load settings first thing after parsing; keep existing exit codes and messages.
- `tests/integration/test_pipeline.py` -- CLI tests `chdir` into `tmp_path`, so no `.env` is found there; keep that pattern.
- `tests/conftest.py` -- folder-based marker hook; add an autouse fixture here that clears every config variable from the environment.
- `.env` (untracked, ignored) -- has `OPENAI_API_KEY`, `OPENAI_MODEL`, `SERPAPI_API_KEY`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`. Never read it in tests or print its values.
- `.gitignore` -- already ignores `.env` and `.env.*` but keeps `.env.example`.
- `pyproject.toml` -- add `pydantic-settings`.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- `uv add pydantic-settings`.
- [x] `src/call_center/config.py` -- `Settings(BaseSettings)` (env_file `.env`, extra ignore, case-insensitive) with the fields and aliases above (use `AliasChoices` for the dual names); `load_settings(**overrides) -> Settings`; `format_config_error(ValidationError) -> str`, which names each bad variable and the allowed values without echoing the input value.
- [x] `src/call_center/cli.py` -- call `load_settings()` after argument parsing; on `ValidationError`, print `invalid configuration: …` to stderr and return 2.
- [x] `.env.example` -- every variable with a safe placeholder or default, plus a comment per group; no real values.
- [x] `tests/conftest.py` -- autouse fixture that `monkeypatch.delenv`s every config variable (all names and aliases).
- [x] `tests/unit/test_config.py` -- matrix rows 1–3 and 6, using `Settings(_env_file=None)`; `GOOGLE_API_KEY` as the alias for the Gemini key; unknown vars ignored; a `.env` file in `tmp_path` is read when passed explicitly.
- [x] `tests/integration/test_pipeline.py` -- matrix rows 4–5 via `main([...])`.

**Acceptance Criteria:**
- Given the user's existing `.env`, when `uv run call-center analyze tests/fixtures/sample.wav` runs, then it succeeds unchanged.
- Given `.env.example` copied to `.env`, when the CLI runs, then it succeeds.

## Implementation Notes

- `env_ignore_empty=True`: blank values in `.env` (e.g. `OPENAI_MODEL=`) fall back to defaults instead of failing bool parsing or yielding empty model names.
- The conftest autouse fixture also sets `Settings.model_config["env_file"] = None`, because `test_cli_custom_out_dir_is_created` does not `chdir` and would otherwise read the real `.env` from the repo root.
- `config.ENV_VARS` (derived from the field aliases) is the single list the fixture clears.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 0, low 0, false 1, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `.env.example` alias names only in comments | false | reject | "Every variable" means every setting; each appears once under its primary name, with aliases documented in comments. Listing two names for one setting would invite conflicting values. |
| — | (lead check) `.env` values in the diff | — | — | Before review, the diff was scanned for every `.env` value of 8 or more characters: only the `OPENAI_MODEL` model name matched, in a test; no secret appears. |

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run call-center analyze tests/fixtures/sample.wav` -- expected: succeeds with the real `.env` present
- `LLM_PROVIDER=claude uv run call-center analyze tests/fixtures/sample.wav; echo $?` -- expected: `invalid configuration: …` and `2`
