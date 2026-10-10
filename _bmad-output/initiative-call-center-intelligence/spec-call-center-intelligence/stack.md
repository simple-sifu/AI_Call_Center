# Stack

## Libraries

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11 or 3.12 | Not 3.13. |
| Orchestration | LangGraph | Typed state machine; one node per pipeline stage. |
| Transcription | faster-whisper (CTranslate2 backend) | int8 quantization; size set by `WHISPER_MODEL_SIZE`. |
| Schemas | Pydantic v2 | Structured LLM output for the summary and QA scores. |
| Persistence | SQLite + SQLAlchemy | Call records and the append-only audit log. |
| Reports | ReportLab | PDF; JSON emitted alongside. |
| UI | Gradio 5.x | Two tabs: Analyze Call, Observability. |
| Tests / lint | pytest, ruff | Unit, integration, and security suites. |
| Tracing | LangSmith | Optional, free tier. |

## Stage mechanics

- **Intake:** detect the format from magic bytes, not the extension; reject files over 50 MB or 60 minutes.
- **Transcription:** cache key is the SHA-256 of the audio bytes.
- **Injection detection:** 22 regex patterns.
- **PII redaction:** SSN, credit card, email, and phone.
- **QA scoring:** the LLM returns dimension scores; Python recomputes the overall and discards any LLM overall.

## LLM providers

Selected by one environment variable through a provider factory; switching needs no code edits.

| Provider | Model | Role | Limits |
|---|---|---|---|
| OpenAI | GPT-4o | Primary; recommended default (provided by the program) | — |
| Google Gemini | 2.0 Flash | Alternative | Free tier, 1,500 req/day |
| Groq | Llama 3.3 70B | Alternative | Free tier, 30 req/min |

## Whisper on CPU

- The first run downloads 1–3 GB of weights, depending on model size.
- Use `WHISPER_MODEL_SIZE=tiny` during development on CPU laptops; large-v3 takes over 25 minutes per call on CPU.
