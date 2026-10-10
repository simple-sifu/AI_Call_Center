---
type: epic
title: "Gradio app"
parent: initiative-call-center-intelligence
covers: [CAP-9, CAP-10]
after: []
assignee: ""
risk: low
---

# Gradio app

## Description

The two-tab Gradio 5.x app: Analyze Call runs the pipeline on an upload and shows its results; Observability shows pipeline performance across stored calls.

## Outcome

A user demos the whole system from a browser; the spec's success signal is met here.

## Done when

1. Uploading a sample call in Analyze Call shows the summary, five dimension scores, and the overall, and offers the PDF and JSON for download.
2. A rejected or blocked call shows its reason, not a stack trace.
3. Observability shows the agreed metrics from the persisted calls.
4. The initiative's success signal demo passes end to end.

## Boundaries

The UI only; it calls the pipeline and reads persisted data, never reimplementing either.

## References

- parent — _bmad-output/initiative-call-center-intelligence/initiative-call-center-intelligence.md
- spec — _bmad-output/initiative-call-center-intelligence/spec-call-center-intelligence/spec-call-center-intelligence.md, CAP-9, CAP-10, Success signal

## Notes

- Waits on epic-reports-audit because: both tabs read what it persists.
