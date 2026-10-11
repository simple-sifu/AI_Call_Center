---
title: 'Pipeline state contract'
type: 'feature'
ticket: '1'
created: '2026-10-10'
status: done
baseline_revision: 'c8cbc2da61a91ea0b2db72594b690a1a803a9e8e'
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

**Problem:** The pipeline state is a placeholder (`source_file`, `stages_completed`). Epics 2–6 each need a fixed, typed shape to read and write, or they will invent incompatible ones.

**Approach:** Define Pydantic v2 value models for the transcript, redacted transcript, summary, QA scores, and audit events, plus a run status. Put them in `PipelineState`, update the seven stubs to emit valid placeholder values and an audit event, and have the graph stop routing to LLM stages once a run is blocked or failed.

## Boundaries & Constraints

**Always:**
- QA weights are fixed: professionalism 0.15, empathy 0.20, resolution 0.30, compliance 0.20, clarity 0.15. The overall score is computed by the model from these weights and is never an input field. An `overall` supplied in input is ignored.
- LLM stages (summarization, qa_scoring) read only `redacted_transcript`, never `transcript`.
- Value models are frozen and reject unknown fields, except QA scores, which ignore extra keys so an LLM-supplied `overall` is dropped.
- `stages_completed` and the CLI keep working unchanged.

**Never:** real stage logic; settings or env; CI; any change to `cli.py`.

**Decisions (user, 2026-10-10):**
- Score scale: each dimension is an integer 1–10; overall = weighted mean × 10, rounded to 1 decimal (range 10.0–100.0).
- Blocked or failed run: skip the remaining stages and go straight to the report stage, so the call is still recorded with its reason and audit trail.
- Sentiment trajectory: exactly three phases in order (opening, middle, closing), each labeled negative, neutral, or positive.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | stub pipeline on `sample.wav` | final state has transcript, redacted_transcript, summary, scores, 7 audit events (all `ok`), status `completed` | No error expected |
| Segment end before start | `TranscriptSegment(start=5, end=2)` | rejected | `ValidationError` |
| Score out of range | a dimension score of 0 or 11 | rejected | `ValidationError` |
| LLM overall supplied | scores dict with `overall: 99` | `overall` equals the weighted computation, not 99 | No error |
| Blocked at injection | injection stage sets status `blocked` with a reason | pii_redaction, summarization, qa_scoring do not run; report runs; status stays `blocked`; audit shows `blocked` at injection_detection then `ok` at report | No exception |

</frozen-after-approval>

## Code Map

- `src/call_center/state.py` -- current placeholder `PipelineState` TypedDict with an `operator.add` reducer on `stages_completed`; extend it, keeping both existing keys.
- `src/call_center/stages/*.py` -- 7 stubs, each `NAME` + `run(state) -> dict`; all import only `call_center.state`.
- `src/call_center/graph.py` -- `STAGES` list and linear `add_edge` chain; `run_pipeline(path)` seeds `source_file` and `stages_completed`.
- `src/call_center/cli.py` -- reads `state["source_file"]` and `state["stages_completed"]` only; do not edit.
- `tests/unit/test_stages.py` -- asserts `NAME in result["stages_completed"]`; keep that contract.
- `tests/integration/test_pipeline.py`, `tests/security/test_stage_order.py` -- must keep passing.
- `pyproject.toml` -- add `pydantic>=2` as an explicit dependency (it is already present transitively via langgraph).

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- add `pydantic>=2`.
- [x] `src/call_center/models.py` -- `TranscriptSegment`, `Transcript` (segments, `audio_sha256`), `Summary` (call_purpose, action_items, sentiment_trajectory, entities), `Entity` (text, type), `DimensionScore` (score, rationale), `QAScores` (five dimensions plus computed `overall`), `QA_WEIGHTS`, `AuditEvent` (stage, at as UTC datetime, outcome ok/blocked/failed, detail), `RunStatus` literal (running/completed/blocked/failed).
- [x] `src/call_center/state.py` -- add `transcript`, `redacted_transcript`, `summary`, `qa_scores` (each optional; `None` until its stage runs), `audit: Annotated[list[AuditEvent], operator.add]`, `status`, `status_reason`.
- [x] `src/call_center/stages/*.py` -- each stub returns a valid placeholder value for its own field plus one `ok` AuditEvent; report sets status `completed` when status is still `running`.
- [x] `src/call_center/graph.py` -- seed status `running` and empty audit; after each stage, a conditional edge sends a blocked or failed run straight to the report stage.
- [x] `tests/unit/test_models.py` -- matrix rows 2–4; weights sum to 1; overall determinism.
- [x] `tests/integration/test_pipeline.py` -- add matrix row 1 (final state validates and has 7 ok audit events).
- [x] `tests/security/test_blocked_run.py` -- matrix row 5, with injection monkeypatched to block; also a test that the summarization and qa_scoring stub sources reference `redacted_transcript` and not `state["transcript"]`.

**Acceptance Criteria:**
- Given the contract, when the user reviews `models.py` and `state.py`, then they approve it before the story is marked built (hitl).
- Given any stage module, when it is replaced with real logic that honours these models, then no other stage module needs editing.

## Implementation Notes

- `sentiment_trajectory` is a `SentimentTrajectory` model with `opening`/`middle`/`closing` fields, so "exactly three phases in order" is enforced structurally.
- `redacted_transcript` reuses the `Transcript` model (no separate redacted type).
- `TranscriptSegment` also carries `speaker`; `end == start` is allowed, `end < start` rejected. `audio_sha256` must be 64 lowercase hex chars.
- `AuditEvent.at` requires a timezone-aware datetime (defaults to now, UTC) and is normalised to UTC.
- Stubs import `call_center.models` in addition to `call_center.state`; still no stage imports another stage. Stubs read state with `.get()` so the existing unit test's minimal state still works; report treats a missing status as `running`.
- Graph: every edge into a non-report stage is conditional on `status not in ("blocked", "failed")`; otherwise it routes to report. The edge into report is plain.

- User approved the contract (`models.py`, `state.py`) on 2026-10-10, after the review patches; hitl acceptance criterion met.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 2, low 4, false 1, maybe-false 0.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `stages/pii_redaction.py` | medium | patch | Stub copies the raw transcript into `redacted_transcript`; a real transcription stage would feed PII to the LLM stages. Fix: stub emits `[REDACTED]` text. |
| 2 | `models.py` list fields | medium | patch | `frozen` is shallow; the reviewer reproduced placeholder mutation leaking across runs and redacted/raw segments aliasing. Fix: tuple fields. |
| 3 | `models.py` `DimensionScore.score` | low | patch | Lax mode accepts `True`, `"7"`, `5.0`. Fix: strict int. |
| 4 | `models.py` `TranscriptSegment` | low | patch | `end=inf` validates. Fix: reject inf and NaN. |
| 5 | `graph.py` START edge | low | reject | Harmless, since `run_pipeline` always seeds `running`; the fix adds a branch for an unreachable case. |
| 6 | `tests/security/test_blocked_run.py` | low | patch | The source regex is bypassable and forces dummy reads in the stubs. Fix: a runtime guard mapping that raises on `transcript` access; dummy reads removed. |
| 7 | hitl acceptance criterion | false | reject | Not a code defect; user sign-off is obtained at presentation, before `built`. |

## Design Notes

The top-level state stays a TypedDict, so LangGraph's partial-update merge and reducers work as in 1.2. The values inside are Pydantic models. `QAScores.overall` is a `@computed_field`, which is why an LLM cannot set it.

```python
class QAScores(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    professionalism: DimensionScore; empathy: DimensionScore; resolution: DimensionScore
    compliance: DimensionScore; clarity: DimensionScore
    @computed_field
    def overall(self) -> float: ...  # round(sum(w * score) * 10, 1)
```

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, including the new unit and security tests
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run call-center analyze tests/fixtures/sample.wav` -- expected: unchanged output, 7 stages
