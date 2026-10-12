# Call Center Intelligence

A seven-stage [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline that turns recorded call audio into a redacted transcript, structured summary, deterministic QA score, PDF/JSON reports, and an append-only audit trail. A Gradio web UI provides **Analyze Call** and **Observability** tabs.

**Python:** 3.11 or 3.12 only (not 3.13).

## Pipeline

Stages run in order. No LLM runs until injection screening and PII redaction succeed.

1. **Intake** — WAV validation (magic bytes), size and duration limits  
2. **Transcription** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper), speaker labels, SHA-256 transcript cache  
3. **Injection detection** — 22 patterns; blocked calls skip LLM stages  
4. **PII redaction** — SSN, card, email, phone (redacted text only in reports/DB)  
5. **Summarization** — structured `Summary` via the configured LLM provider  
6. **QA scoring** — five dimensions (1–10); **overall is computed in Python**, not taken from the model  
7. **Report** — JSON + PDF, SQLite row, audit events  

Provider switching: set **`LLM_PROVIDER`** to `openai`, `gemini`, or `groq` (no code changes).

## Quick start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.11/3.12 with pip  
- API key for your chosen LLM provider  
- CPU-friendly ASR: use `WHISPER_MODEL_SIZE=tiny` while developing (first run downloads model weights, ~1–3 GB depending on size)

### Install

```bash
git clone https://github.com/simple-sifu/AI_Call_Center.git
cd AI_Call_Center
uv sync
cp .env.example .env
# Edit .env: add OPENAI_API_KEY (or Gemini/Groq) and review defaults
```

### Web UI (demo)

```bash
uv run call-center ui
```

Open http://127.0.0.1:7860

- **Analyze Call:** upload a WAV (recommended: `tests/fixtures/call_mono.wav` or `call_stereo.wav`). Avoid `sample.wav` for live Whisper demos — it is only 1 s and often transcribes to zero segments.  
- **Observability:** refresh to see persisted runs from SQLite.

Options: `uv run call-center ui --host 0.0.0.0 --port 7860` (optional `--share` for a temporary public Gradio link).

### CLI

```bash
uv run call-center analyze tests/fixtures/call_mono.wav
```

- Writes `reports/<stem>.json` and `.pdf`, persists to `call_center.db`.  
- Exit `0` on completed; exit `2` on failed/blocked (reason on stderr).  
- Custom output directory: `--out /path/to/reports`

### Switch LLM provider

Set in `.env` or the shell, then re-run analyze or restart the UI:

```bash
LLM_PROVIDER=openai uv run call-center analyze tests/fixtures/call_mono.wav
LLM_PROVIDER=gemini uv run call-center analyze tests/fixtures/call_mono.wav
LLM_PROVIDER=groq   uv run call-center analyze tests/fixtures/call_mono.wav
```

Only the selected provider’s API key is required.

## Configuration

See [`.env.example`](.env.example). Common variables:

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` | `openai` \| `gemini` \| `groq` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` | Provider credentials |
| `WHISPER_MODEL_SIZE` | `tiny` (dev) … `large-v3` (slow on CPU) |
| `AGENT_CHANNEL` | `left` \| `right` for stereo agent channel |
| `REPORT_OUTPUT_DIR` | Default `reports/` |
| `DATABASE_URL` | Default `sqlite:///call_center.db` |
| `TRANSCRIPT_CACHE` | `on` \| `off` — cache raw ASR segments under `.cache/transcripts` |
| `LANGSMITH_TRACING` | Optional tracing when `true` and key set |

## Development

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
```

Markers (see `pyproject.toml`):

- Default: unit + integration + security (no real ASR/LLM)  
- `pytest -m slow` — real Whisper (opt-in)  
- `pytest -m live` — real LLM calls, reads your `.env` (opt-in)

## Project layout

| Path | Role |
|------|------|
| `src/call_center/graph.py` | LangGraph wiring |
| `src/call_center/stages/` | One module per pipeline stage |
| `src/call_center/llm.py` | Multi-provider chat model factory |
| `src/call_center/reports.py` | JSON/PDF report shapes and writers |
| `src/call_center/persistence.py` | SQLite calls + append-only audit |
| `src/call_center/gradio_app.py` | Gradio UI |
| `tests/fixtures/` | Sample WAV files for manual demo and tests |

## Outputs (local, git-ignored)

- `reports/` — JSON and PDF per analyzed file  
- `call_center.db` — call rows and audit events  
- `.cache/transcripts/` — raw ASR cache (may contain unredacted text)

## License / course context

Built as a graded call-center intelligence project: typed pipeline state, security gates before LLM access, deterministic QA weighting, provider abstraction, and broad automated test coverage.
