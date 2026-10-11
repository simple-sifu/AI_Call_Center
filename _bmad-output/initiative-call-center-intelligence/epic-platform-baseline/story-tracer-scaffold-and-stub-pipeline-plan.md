---
title: 'Tracer: scaffold and stub pipeline'
type: 'feature'
ticket: '2'
created: '2026-10-10'
status: 'built'
baseline_revision: '119c5d564c035109d8f1673c84750ab96b85f41d'
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

**Problem:** There is no code, and the venv is on Python 3.14, which the spec forbids. Every later epic needs a runnable 7-stage graph where it can replace one stub stage.

**Approach:** Scaffold a uv-managed `call_center` package on Python 3.12. Add seven stub stage modules wired in fixed order by a LangGraph graph, plus an `analyze <file>` CLI that writes a JSON report, pytest suites with markers, and ruff config.

## Boundaries & Constraints

**Always:**
- `requires-python = ">=3.11,<3.13"`; the venv runs on 3.12, pinned with `.python-version`.
- One module per stage. The stage order lives in one list in `graph.py`; a stage module never imports another stage.
- Stage order: intake → transcription → injection_detection → pii_redaction → summarization → qa_scoring → report.
- The only runtime dependency is `langgraph`. Dev dependencies are `pytest` and `ruff`. `uv.lock` is committed.

**Never:**
- Real stage logic: no audio validation, whisper, regex, PII, LLM, PDF, or SQLite.
- Settings or `.env` loading (story 1.3), the full state contract (1.1), CI (1.4), or LangSmith (1.5).
- Network access or model downloads in tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | `call-center analyze tests/fixtures/sample.wav` | Writes `reports/sample.json` with `source_file`, `status: "stub"`, `stages_completed` = the 7 names in order; prints the path; exit 0 | No error expected |
| Custom output dir | `analyze <file> --out <dir>` | Report written to `<dir>/<stem>.json`; dir created if missing | No error expected |
| Missing file | `analyze nope.wav` | Nothing written; exit 2 | stderr: `file not found: nope.wav` |
| Path is a directory | `analyze tests/` | Nothing written; exit 2 | stderr: `not a file: tests` |

</frozen-after-approval>

## Code Map

Greenfield: no source code yet. Existing files to respect:
- `.gitignore` -- add `reports/`; `.venv/` and `.env` are already ignored.
- `.venv/` -- Python 3.14.6 with only pip; safe to delete and recreate.
- `_bmad/`, `_bmad-output/`, `.agents/`, `.claude/` -- BMad tooling and plans; do not touch.
- Python 3.12.13 is available at `/opt/homebrew/bin/python3.12`; uv is 0.12.3.

## Tasks & Acceptance

**Execution:**
- [x] `.venv/`, `.python-version` -- `rm -rf .venv`, `uv python pin 3.12`, `uv venv --python 3.12` -- the spec forbids 3.13+.
- [x] `pyproject.toml` -- project `call-center` with the `uv_build` backend and src layout; `requires-python`; dependency `langgraph`; dev group `pytest`, `ruff`; script `call-center = "call_center.cli:main"`; `[tool.ruff]` (target py311, line-length 100, select E,F,I,B,UP); `[tool.pytest.ini_options]` (testpaths `tests`, `--strict-markers`, markers `unit`, `integration`, `security`) -- one config home.
- [x] `src/call_center/__init__.py` -- package marker with `__version__`.
- [x] `src/call_center/state.py` -- minimal `PipelineState` TypedDict: `source_file: str`, `stages_completed: Annotated[list[str], operator.add]` -- a placeholder that story 1.1 replaces.
- [x] `src/call_center/stages/{intake,transcription,injection_detection,pii_redaction,summarization,qa_scoring,report}.py` -- each defines `NAME` and `run(state) -> dict` returning `{"stages_completed": [NAME]}`.
- [x] `src/call_center/graph.py` -- `STAGES` ordered list of modules; `build_graph()` compiles a StateGraph chaining them START→…→END; `run_pipeline(path) -> dict`.
- [x] `src/call_center/cli.py` -- argparse `analyze <file> [--out reports]`; validate per the I/O matrix; write the JSON report; `main(argv=None) -> int`.
- [x] `tests/fixtures/make_sample.py`, `tests/fixtures/sample.wav` -- stdlib `wave` writes a 1 s 440 Hz 16 kHz mono tone; commit both (about 32 KB).
- [x] `tests/conftest.py` -- auto-apply the `unit`/`integration`/`security` marker from the test's folder.
- [x] `tests/unit/test_stages.py` -- each stage returns its own name; `STAGES` has 7 unique names.
- [x] `tests/integration/test_pipeline.py` -- `run_pipeline` gives the 7 names in order; CLI cases from the I/O matrix via `main([...])` with `tmp_path`.
- [x] `tests/security/test_stage_order.py` -- injection_detection and pii_redaction both come before summarization and qa_scoring in `STAGES` -- guards the spec's no-LLM-before-screening constraint.
- [x] `.gitignore` -- add `reports/`.

**Acceptance Criteria:**
- Given a fresh clone with uv, when `uv sync` runs, then the venv is Python 3.12.x and `uv run python -c "import call_center"` succeeds.
- Given the repo, when `uv run pytest -m security` runs, then only the security tests are selected and pass, and likewise for `-m unit` and `-m integration`.
- Given a new stage implementation, when one stage module is replaced, then no other stage module and no test outside that stage needs editing (each stage is self-contained).

## Implementation Notes

- Added `extend-exclude = [".agents", ".claude", "_bmad", "_bmad-output"]` to `[tool.ruff]`: `ruff check .` failed on BMad's vendored scripts, which this story must not touch.
- Added a docstring-only `src/call_center/stages/__init__.py`.
- The CLI strips a trailing `/` in the not-a-file message so `analyze tests/` prints `not a file: tests`, as the matrix specifies.
- `langgraph` is unpinned in `pyproject.toml`; `uv.lock` fixes the version.
- Verified: Python 3.12.13; 14 tests pass (unit 8, integration 5, security 1); ruff check and format are clean; the CLI writes the 7-stage report; a fresh `uv sync` rebuilds on 3.12. Matrix audit: all 4 rows covered by passing tests.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 1, low 4, false 1, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `tests/unit/test_stages.py` | medium | patch | Exact-dict assert fails once any real stage returns more keys, forcing edits to a shared test (AC3). Fix: assert NAME in `stages_completed`. |
| 2 | `tests/integration/test_pipeline.py` happy path | low | patch | Exact report dict couples the test to future keys. Fix: assert the three required keys only. |
| 3 | `tests/conftest.py` | low | patch | Markers come from absolute path parts; a parent dir named `security` tags all tests (AC2). Fix: use the path relative to `tests/`. |
| 4 | `cli.py` `--out` pointing at an existing file | low | reject | Real traceback, but rare in use and the fix adds a new guard branch. |
| 5 | `cli.py` `rstrip('/')` | low | patch | `analyze /` prints an empty name. Fix: `str(Path(args.file))`. |
| 6 | `.gitignore` `_bmad/render/` | false | reject | The user asked for this rule before the build started; it is in the diff only because it was uncommitted at baseline. |

## Design Notes

LangGraph merges each node's returned dict into state. The `operator.add` reducer on `stages_completed` makes each stub append its name, so the order is proven from state rather than asserted by the graph code.

```python
graph = StateGraph(PipelineState)
for m in STAGES: graph.add_node(m.NAME, m.run)
graph.add_edge(START, STAGES[0].NAME)
for a, b in zip(STAGES, STAGES[1:]): graph.add_edge(a.NAME, b.NAME)
graph.add_edge(STAGES[-1].NAME, END)
```

## Verification

**Commands:**
- `uv run python --version` -- expected: Python 3.12.x
- `uv run call-center analyze tests/fixtures/sample.wav` -- expected: prints `reports/sample.json`; the file lists the 7 stages in order
- `uv run pytest` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
