- source_plan: `_bmad-output/initiative-call-center-intelligence/epic-audio-intake-transcription/story-tracer-real-transcription-plan.md`
  summary: The CLI exits 0 and writes `"status": "stub"` even when a run ends `failed`, so a broken stage looks like success from the command line.
  evidence: Story 2.1 review; `cli.main` never reads `state["status"]`. Story 2.5 already makes the CLI print `rejected: <reason>` and exit 2 on intake rejection; widen that to any `failed` or `blocked` run.
