---
id: SPEC-call-center-intelligence
companions:
  - stack.md
  - pipeline-diagram.md
sources:
  - ../brief-call-center-intelligence/brief-call-center-intelligence.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Call Center Intelligence System

## Why

Pain plus mandate. A mid-size call center takes ~5,000 calls/day; QA staff manually review under 5% at ~15 minutes each. So 95% of calls get no review and coaching is lost, reviewers agree on the same call only 40–60% of the time, and problems surface the day after, too late to correct. In regulated industries (finance, healthcare) this is a compliance liability: no audit trail and no proof required disclosures were made. The system analyzes every uploaded call automatically, scores it consistently, and leaves an auditable record.

## Capabilities

- **CAP-1** Intake
  - **intent:** The system accepts only genuine audio within limits, judged by file content rather than extension.
  - **success:** A non-audio file renamed to `.wav`/`.mp3` is rejected; a file over 50 MB or over 60 minutes is rejected; a valid file within limits is accepted.
- **CAP-2** Transcription
  - **intent:** The system produces a speaker-labeled transcript of each call, and returns a stored result for audio it has already transcribed.
  - **success:** The transcript segments carry speaker labels; resubmitting byte-identical audio returns the cached transcript (SHA-256 match) without running transcription again.
- **CAP-3** Injection detection
  - **intent:** The system blocks adversarial content in a transcript before any LLM sees it.
  - **success:** A transcript matching any of the 22 injection patterns blocks the call: the remaining analysis stages are skipped and a test proves the LLM client is never invoked. The report stage still records the call with the block reason and its audit trail.
- **CAP-4** PII redaction
  - **intent:** The system removes SSNs, credit card numbers, emails, and phone numbers from the transcript before any LLM call (GDPR/CCPA).
  - **success:** For a transcript seeded with each PII type, the text sent to the LLM contains none of them.
- **CAP-5** Structured summary
  - **intent:** A QA user gets a structured summary of each call: purpose, action items, a sentiment trajectory over three phases (opening, middle, closing; each negative, neutral, or positive), and entities.
  - **success:** The output validates against the summary schema; schema-invalid LLM output is rejected or retried, never passed on silently.
- **CAP-6** QA scoring
  - **intent:** Each call is scored on five weighted dimensions, with an overall score that cannot drift with the LLM.
  - **success:** Each dimension is an integer from 1 to 10 with a rationale. For any set of dimension scores, the overall equals `round(weighted mean × 10, 1)` (10.0–100.0), computed in Python; an overall supplied by the LLM is ignored even when it differs.
- **CAP-7** Report and audit trail
  - **intent:** Each analyzed call yields a downloadable PDF and JSON report, a persisted record, and an append-only audit trail.
  - **success:** After analysis, including a blocked or failed one, the PDF and JSON exist, the call's row is in SQLite, and audit entries exist for each stage that ran; the application exposes no path to update or delete audit entries.
- **CAP-8** Provider switching
  - **intent:** An operator switches the LLM between OpenAI, Gemini, and Groq by changing one environment variable.
  - **success:** The same pipeline completes against each provider with only that variable changed, and no code edits.
- **CAP-9** Analyze Call UI
  - **intent:** A user uploads a call recording in a web UI and sees the summary, scores, and report.
  - **success:** Demo: upload a sample call in the Analyze Call tab, see the summary and five dimension scores plus the overall, and download the PDF and JSON.
- **CAP-10** Observability dashboard
  - **intent:** An operator sees how the pipeline is performing across analyzed calls.
  - **success:** The Observability tab shows the agreed metrics (see Open Questions) for persisted calls.

## Constraints

- QA weights are fixed: Professionalism 15%, Empathy 20%, Resolution 30%, Compliance 20%, Clarity 15%. Dimensions are scored 1–10; overall = round(weighted mean × 10, 1).
- Stages exchange data only through the approved pipeline state contract (`src/call_center/models.py`, `src/call_center/state.py`); LLM stages read only the redacted transcript.
- No LLM receives a transcript before injection screening (CAP-3) and PII redaction (CAP-4) have both passed.
- The pipeline is a 7-stage LangGraph graph: Intake → Transcription → Injection Detection → PII Redaction → Summarization → QA Scoring → Report (see `pipeline-diagram.md`).
- Python 3.11 or 3.12 only; not 3.13.
- It must run on a CPU laptop: the whisper model size is set by `WHISPER_MODEL_SIZE` (`tiny` for development; large-v3 takes over 25 minutes per call on CPU), and the first run downloads 1–3 GB of weights.
- The multi-provider factory is mandatory even when the demo runs only OpenAI (20% of the grade).
- 100+ tests across unit, integration, and security suites.
- The free tiers limit the alternative providers: Gemini at 1,500 requests/day and Groq at 30 requests/min. LLM calls per analyzed call must stay small and bounded.
- The stack is fixed; see `stack.md`.

## Non-goals

- Live or streaming call analysis; only recorded audio uploads are in scope.
- Telephony or contact-center platform integration.
- Authentication, user accounts, multi-tenancy.
- A human reviewer workflow (assigning, overriding, or disputing scores).
- Meeting the 5,000 calls/day throughput.

## Success signal

- Uploading a sample call in the Gradio app runs all 7 stages and returns a summary, five dimension scores, and a deterministically computed overall, with PDF and JSON reports and audit entries persisted. Repeating the run with only the provider environment variable changed (OpenAI → Gemini → Groq) also succeeds. The test suite (100+ tests: unit, integration, security) passes.

## Assumptions

- Batch analysis of recorded audio uploads, not live calls.
- A single-user local deployment; no auth or multi-tenancy.
- 5,000 calls/day is the problem backdrop, not a throughput target.
- This is a graded course project; the grading requirements are treated as constraints.
- LangSmith tracing is optional; the pipeline runs without a key.
- The non-goals are inferred, since the source states none; confirm them.

## Open Questions

- Diarization: faster-whisper has none built in. Which tool (e.g. pyannote, which needs a Hugging Face token) or heuristic should provide it?
- What are the 22 injection patterns? (A match blocks the call; decided.)
- Compliance dimension: which required disclosures are checked, and for which industry?
- PII scope beyond SSN, card, email, and phone (names, addresses, date of birth, account numbers, PHI)? Are raw audio and unredacted transcripts stored in the cache or the database?
- Observability dashboard: which metrics (stage latency, tokens/cost, provider, error rate, score distribution)?
- How should LLM retries, timeouts, and malformed output be handled per provider?
