"""Summarization stage: the redacted transcript to a ``Summary`` through ``llm_call``.

Reads only ``redacted_transcript``. The transcript goes to the model as speaker-labelled
lines between ``<transcript>`` delimiters (``prompting``), and the system prompt says it is
data, not instructions. The model answers in structured output, asked for the way the
factory says suits the provider, and the answer is validated with
``Summary.model_validate``; nothing else reaches the state.
``llm_call.invoke_structured_counted`` makes the call and owns the retry budget: at most
3 calls per run, one retry for invalid output and up to two for transient provider
errors.

Any failure (configuration, missing key, provider error, invalid output) sets status
``failed`` with a reason naming the provider, the kind of error and, for a call that was
made, the number of attempts. Reasons hold only exception class names, never transcript
or model text.
"""

from pydantic import ValidationError

from call_center import llm, llm_call, prompting
from call_center.config import format_config_error, load_settings
from call_center.models import AuditEvent, Summary, Transcript
from call_center.state import PipelineState

NAME = "summarization"

SYSTEM_PROMPT = f"""\
You summarize customer service phone calls.

{prompting.TRANSCRIPT_FRAMING}

Return:
- call_purpose: one sentence on why the customer called.
- action_items: concrete follow-ups agreed or required; empty if there are none.
- sentiment_trajectory: the customer's sentiment at the opening, middle and closing of \
the call, each one of negative, neutral or positive.
- entities: products, organizations, places, dates, amounts and other named things \
mentioned, each with its text and a short lowercase type such as product, organization, \
date, amount or placeholder.
"""

# Kept as this module's names for callers and tests; the rendering lives in ``prompting``.
OPEN, CLOSE = prompting.OPEN, prompting.CLOSE
render_transcript = prompting.render_transcript


def messages(transcript: Transcript) -> list:
    return prompting.transcript_messages(SYSTEM_PROMPT, transcript)


def _failed(cause: str) -> dict:
    reason = f"summarization failed: {cause}"
    return {
        "stages_completed": [NAME],
        "status": "failed",
        "status_reason": reason,
        "audit": [AuditEvent(stage=NAME, outcome="failed", detail=reason)],
    }


def run(state: PipelineState) -> dict:
    redacted = state.get("redacted_transcript")
    if not isinstance(redacted, Transcript):
        return _failed("no redacted transcript")
    try:
        settings = load_settings()
    except ValidationError as error:
        return _failed("invalid configuration: " + format_config_error(error))
    provider = settings.llm_provider
    try:
        model = llm.get_chat_model(settings)
    except llm.LLMConfigError as error:
        return _failed(str(error))
    try:
        summary, attempts = llm_call.invoke_structured_counted(
            model, provider, Summary, messages(redacted)
        )
    except llm_call.LLMCallError as error:
        return _failed(call_failure(error))
    detail = f"summarized with {provider} {llm.model_name(settings)}"
    if attempts > 1:
        detail += f" after {attempts} attempts"
    return {
        "stages_completed": [NAME],
        "summary": summary,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail=detail)],
    }


def call_failure(error: llm_call.LLMCallError) -> str:
    """The failure cause for a failed call; qa_scoring words its failures the same way."""
    if error.kind == "invalid_output":
        cause = f"{error.provider} returned invalid output"
    else:
        cause = f"{error.provider} provider error ({error.error_class})"
    return f"{cause} after {error.attempts} attempts"
