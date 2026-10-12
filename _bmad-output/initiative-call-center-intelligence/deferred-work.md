- source_plan: `_bmad-output/initiative-call-center-intelligence/epic-audio-intake-transcription/story-tracer-real-transcription-plan.md`
  summary: The CLI exits 0 and writes `"status": "stub"` even when a run ends `failed`, so a broken stage looks like success from the command line.
  evidence: Story 2.1 review; `cli.main` never reads `state["status"]`. Story 2.5 already makes the CLI print `rejected: <reason>` and exit 2 on intake rejection; widen that to any `failed` or `blocked` run.
- source_plan: `_bmad-output/initiative-call-center-intelligence/epic-audio-intake-transcription/story-speaker-labeling-plan.md`
  summary: Stereo files are decoded a second time, fully in memory, to compute channel energy (about 700 MB extra peak for a 60-minute call).
  evidence: Story 2.3 review; `asr.load_channels` calls `decode_audio(split_stereo=True)` after the transcriber has decoded the mix. Fix candidate for the 2.6 sweep: stream PyAV frames into a per-channel RMS envelope (e.g. 10 ms windows), or decode once and share the audio with the transcriber.
- resolved: the CLI-exit entry above (`cli.main` exits 0 on a failed run) is resolved by story 2.5 (`epic-audio-intake-transcription/story-intake-validation-plan.md`): after writing the report, a `failed` run prints its `status_reason` and a `blocked` run prints `blocked: <reason>` to stderr, and both exit 2.
- resolved: the stereo second-decode entry above is resolved by story 2.6 (`epic-audio-intake-transcription/story-refactor-sweep-plan.md`): `asr.load_channels` streams a per-10 ms RMS envelope; peak traced memory for a 50 MB stereo file was 9.2 MB, against about 100 MB of floats before.
- source_plan: `_bmad-output/initiative-call-center-intelligence/epic-transcript-safety/story-pii-redaction-plan.md`
  summary: A PII value split across segments in the middle of a digit group (["123-45-67", "89"]) is not redacted; revisit with story 3.4 (spoken-number PII).
  evidence: Review pass 4 reproduced it (counts 0). Joining digit-to-digit at every segment break reopens the over-matching seen in passes 1-3; the user accepted it as a known gap (2026-10-11).
