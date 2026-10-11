---
type: epic
title: "Platform baseline and stub pipeline"
parent: initiative-call-center-intelligence
covers: []
after: []
assignee: ""
risk: medium
---

# Platform baseline and stub pipeline

## Description

The project scaffold, test and lint tooling, CI, configuration, and a 7-stage LangGraph graph of stub stages that runs a sample file end to end. It also fixes the pipeline state contract every later epic builds against.

## Outcome

Every later epic starts by replacing one stub stage in a graph that already runs, against a state contract that is already agreed.

## Requirements

- B1: Scaffold on Python 3.11 or 3.12, managed with uv. (spec, Constraints)
- B2: A 7-stage LangGraph graph in the fixed order, one module per stage. (spec, Constraints; pipeline-diagram.md)
- B3: A typed pipeline state contract shared by all stages. (initiative, Notes)
- B4: pytest unit, integration, and security suites, plus ruff. (spec, Constraints)
- B5: Configuration from env: provider, API keys, `WHISPER_MODEL_SIZE`, LangSmith. (spec, Constraints; stack.md)
- B6: LangSmith tracing is optional and off without a key. (spec, Assumptions)
- B7: CI runs lint and tests on 3.11 and 3.12. (spec, Constraints)

## Done when

1. `uv run pytest` passes with unit, integration, and security suite folders in place, and `ruff check` is clean, locally and in CI on Python 3.11 and 3.12.
2. One CLI command runs a sample audio file through all 7 stub stages in order and writes a stub JSON report.
3. The pipeline state contract (transcript segments, summary, scores, per-stage audit events, blocked/failed status) is defined as typed models and agreed by the user.
4. Each stage is its own module behind the graph, so replacing a stage touches only that module.
5. With LangSmith env vars set, a run appears as a trace; without them, the run still succeeds.

## Boundaries

Scaffold, config, the graph skeleton, the state contract, and tracing. No real stage logic; each later epic owns its stage.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, sections Constraints, Assumptions
- stack — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/stack.md
- diagram — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/pipeline-diagram.md

## Notes

- Decision: the shared state contract is entry 1 here (hitl); epics 2–6 wait on it.
- Source conflict: spec Constraints say Python 3.11 or 3.12 vs the existing .venv on Python 3.14.6; entry 2 rebuilds it on 3.12 (3.12.13 is installed).
- Decision: uv as the package manager and pydantic-settings for configuration (approved with the breakdown, 2026-10-10).
- Decision: Refactor sweep closes the epic (approved with the breakdown, 2026-10-10).
