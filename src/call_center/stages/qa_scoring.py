"""QA scoring stage: the redacted transcript to ``QAScores`` through ``llm_call``.

Reads only ``redacted_transcript``, framed exactly as summarization frames it
(``prompting``). The system prompt is built from ``rubric`` on every call, so editing
``rubric.COMPLIANCE_CHECKS`` changes what the model is asked. The model scores the five
dimensions 1-10 with a rationale each; the schema it is sent holds only those five
(``QAScores``' validation schema has no ``overall``). Any ``overall`` it returns is dropped
by ``QAScores``, whose ``overall`` is always computed from ``models.QA_WEIGHTS``. A score
outside 1-10, not an integer, or missing is invalid output, retried once by
``llm_call.invoke_structured_counted``, which owns the retry budget.

Any failure sets status ``failed`` with a reason in summarization's wording, holding only
the provider, the kind of error, exception class names and attempt counts, never
transcript or model text. The summary stays in the state and the graph routes to report.
"""

from pydantic import ValidationError

from call_center import llm, llm_call, prompting, rubric
from call_center.config import format_config_error, load_settings
from call_center.models import AuditEvent, QAScores, Transcript
from call_center.stages.summarization import call_failure
from call_center.state import PipelineState

NAME = "qa_scoring"

_PROMPT_HEAD = """\
You assess the quality of customer service phone calls, scoring the agent's handling of \
the call against a rubric."""

_PROMPT_TAIL = """\
Score each of professionalism, empathy, resolution, compliance and clarity as a whole \
number from 1 to 10, using the bands in the rubric, and give each a short rationale that \
points to what happened in the call. Score only what the transcript shows; when the \
transcript holds no evidence for a check, count it as not met. Do not return an overall \
score; it is computed from your dimension scores."""


def system_prompt() -> str:
    """The QA system prompt, built from ``rubric`` as it is now."""
    return "\n\n".join(
        [
            _PROMPT_HEAD,
            prompting.TRANSCRIPT_FRAMING_SCORING,
            "Rubric:\n\n" + rubric.render(),
            _PROMPT_TAIL,
        ]
    )


def messages(transcript: Transcript) -> list:
    return prompting.transcript_messages(system_prompt(), transcript)


def _failed(cause: str) -> dict:
    reason = f"qa_scoring failed: {cause}"
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
        scores, attempts = llm_call.invoke_structured_counted(
            model, provider, QAScores, messages(redacted)
        )
    except llm_call.LLMCallError as error:
        return _failed(call_failure(error))
    detail = f"scored with {provider} {llm.model_name(settings)}, overall {scores.overall}"
    if attempts > 1:
        detail += f" after {attempts} attempts"
    return {
        "stages_completed": [NAME],
        "qa_scores": scores,
        "audit": [AuditEvent(stage=NAME, outcome="ok", detail=detail)],
    }
