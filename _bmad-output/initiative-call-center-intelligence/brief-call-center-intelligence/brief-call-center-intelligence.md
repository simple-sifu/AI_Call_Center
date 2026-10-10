Call Center Intelligence System

A mid-size call center handles roughly 5,000 calls per day. QA teams manually review fewer than 5% of them, taking about 15 minutes per review. This creates three compounding falures: 95% of calls receive zero quality review(coaching opportunities lost), human reviewers only agree on the same call 40%-60% of the time (inconsistent and unfair scoring), and reviews surface problems day after the call (too late to coach or correct). In regulated industries like finance and healthcare, this is also a compliance liability - there's no audit trail and no way to prove required disclosures were made.

Proposed Solution
A production-grade 7-stage LangGraph pipeline that processes call audio end-to-end:
1. Intake - magic-byte format validation (not file extension), 50MB and 60-minute limits.
2. Transcription - faster-whisper with int8 quantization, speaker diarization, SHA-256 caching so identical audio returns instantly.
3. Injection Detection - 22 regex patterns block adversarial audio before any LLM sees the transcript
4. PII Redaction - strips SSN, credit card, email, and phone before the LLM call (GDPR/CCPA Safety)
5. Summarization - structured Pydantic output: call purpose, action items, sentiment trajectory, entities.
6. QA Scoring - five weighted dimensions (Professionalism 15%, Empathy 20%, Resolution 30%, Compliance 20%, Clarity 15%); the overall score is always recomputed deterministically in Python -- the LLM's score is discarded as a guardrail against scoring drift.
7. Report - PDF and JSON generation via ReportLab, SQLite persistence, append-only audit log.

A Gradio app with two tabs (Analyze Call, Observability dashboard) and 100+ tests across unit, integration, and security suities. A multi-provider LLM factory makes switching between OpenAI, Gemini, and Groq a single environment variable change -- no code edits required, which is itself a graded requirement.

Tech Stack
Python 3.11+, LangGraph, faster-whisper (CTranslate2 backend), Pydantic v2, SQLite + SQLAlchemy, ReportLab for PDFs, Gradio 5.x, pytest, ruff. LangSmith for tracing.

External APIs & Services Required
- Service: OpenAI API (GPT-4o) | Purpose: Primary LLM for analysis | Notes: Provided by the program - recommended default.
- Service: Google Gemini 2.0 Flash | Purpose: Alternative LLM | Notes: Free 1,500 req/day - students must still wire up the provider factor for full marks.
- Service: Groq Llama 3.3 70B | Purpose: Alternative LLM | Notes: Fee 30 req/min - same as above.
- Service: LangSmith | Purpose: Tracing/observability | Notes: Free tier, optional
Heads up: This is the most demanding project. Faster-whisper downloads model weights on first run (1-3 GB depending on size). On CPU laptops, students must use WHISPER_MODEL_SIZE=tiny during development-large v3 takes 25+ minutes per call on CPU. Python 3.11 or 3.12 only, not 3.13. Also: students still need to implement the multi-provider factory (its worth 20% of the grade) even though they'll likely run with OpenAI for the demo.

Difficulty: Hard
Recommended for students with strong Python fundamentals who want production engineering experience: typed state machines, security layers, deterministic scoring, multi-provider abstraction, and 100+ tests.