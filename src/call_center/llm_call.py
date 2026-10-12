"""Structured LLM calls with validation and a fixed retry budget, shared by the LLM stages.

``invoke_structured`` asks the model the stage built for ``schema`` (the way
``llm.structured_output_args`` says suits the provider), validates the answer with
``schema.model_validate`` and returns the validated instance. It makes at most
``MAX_CALLS`` calls, whatever the input:

- Invalid output (the answer cannot be parsed, or fails validation): one retry. The retry
  repeats the messages and adds one message listing what was wrong, as field paths and
  pydantic error types only, never the model's text or the transcript.
- Transient provider errors (rate limit 429, timeout or 408, connection failure,
  5xx): up to two
  retries, after ``BACKOFF_S`` seconds (2 s, then 4 s). Any other error fails at once.

Both kinds share the budget. When it runs out, or an error cannot be retried, the helper
raises ``LLMCallError`` with the failure kind, the provider, the last error's class name
and the number of calls made; it holds no provider or model text. The clients make one
attempt each (``llm``), so this is the only retry layer. Backoff goes through ``sleep``,
which tests replace.
"""

import functools
import json
import time
from collections.abc import Iterator, Sequence
from typing import Any, Literal, TypeVar

from langchain_core.exceptions import (
    ContextOverflowError,
    ModelAuthenticationError,
    ModelError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    OutputParserException,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, ValidationError

from call_center import llm
from call_center.config import LLMProvider

MAX_CALLS = 3
MAX_INVALID_RETRIES = 1
BACKOFF_S = (2.0, 4.0)  # before the first and second transient retry

FailureKind = Literal["invalid_output", "provider_error"]
T = TypeVar("T", bound=BaseModel)

# Output the model gave that is not a valid answer.
_INVALID_OUTPUT = (ValidationError, OutputParserException, json.JSONDecodeError)
# langchain's provider-neutral errors that say a retry cannot help.
_NOT_RETRYABLE = (
    ModelAuthenticationError,
    ModelPermissionDeniedError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ContextOverflowError,
)
_CHAIN_DEPTH = 8


class LLMCallError(Exception):
    """A structured call failed. Holds no provider, model or transcript text."""

    def __init__(
        self, kind: FailureKind, provider: LLMProvider, error_class: str, attempts: int
    ) -> None:
        self.kind = kind
        self.provider = provider
        self.error_class = error_class
        self.attempts = attempts
        super().__init__(f"{provider} {kind} ({error_class}) after {attempts} attempts")


def sleep(seconds: float) -> None:
    """Backoff before a transient retry; the one place the helper waits (tests patch it)."""
    time.sleep(seconds)


def invoke_structured(
    model: BaseChatModel,
    provider: LLMProvider,
    schema: type[T],
    messages: Sequence[BaseMessage],
) -> T:
    """The validated ``schema`` answer to ``messages``; raises ``LLMCallError``."""
    value, _ = invoke_structured_counted(model, provider, schema, messages)
    return value


def invoke_structured_counted(
    model: BaseChatModel,
    provider: LLMProvider,
    schema: type[T],
    messages: Sequence[BaseMessage],
) -> tuple[T, int]:
    """``invoke_structured``, also returning how many calls it made (for the audit)."""
    try:
        structured = model.with_structured_output(**llm.structured_output_args(provider, schema))
    except Exception as error:
        raise LLMCallError("provider_error", provider, type(error).__name__, 1) from None

    base = list(messages)
    correction: list[BaseMessage] = []
    invalid_retries = transient_retries = 0
    for attempt in range(1, MAX_CALLS + 1):
        try:
            answer = structured.invoke(base + correction)
            if isinstance(answer, BaseModel):
                answer = answer.model_dump()
            return schema.model_validate(answer), attempt
        except _INVALID_OUTPUT as error:
            if invalid_retries >= MAX_INVALID_RETRIES or attempt == MAX_CALLS:
                raise LLMCallError(
                    "invalid_output", provider, type(error).__name__, attempt
                ) from None
            invalid_retries += 1
            correction = [HumanMessage(content=correction_message(error, schema))]
        except Exception as error:  # every provider failure; none escapes as itself
            if not is_transient(error) or attempt == MAX_CALLS:
                raise LLMCallError(
                    "provider_error", provider, type(error).__name__, attempt
                ) from None
            sleep(BACKOFF_S[transient_retries])
            transient_retries += 1
    raise AssertionError("unreachable: every attempt returns or raises")  # pragma: no cover


# Invalid output


def correction_message(error: Exception, schema: type[BaseModel]) -> str:
    """What was wrong with the last answer: field paths and pydantic error types only."""
    lines = [
        "Your previous answer did not match the required structured output.",
    ]
    if isinstance(error, ValidationError):
        known = _field_names(schema)
        problems = sorted({(_path(e["loc"], known), e["type"]) for e in error.errors()})
        lines.append("Problems (field: error type):")
        lines += [f"- {path}: {kind}" for path, kind in problems]
    else:
        lines.append("It could not be parsed as the requested schema.")
    lines.append("Answer again with every required field and no other fields.")
    return "\n".join(lines)


def _path(loc: tuple[Any, ...], known: frozenset[str]) -> str:
    # Keys the model invented (an extra field) are model text, so they are never echoed.
    parts = [str(p) if isinstance(p, int) or p in known else "<unexpected field>" for p in loc]
    return ".".join(parts) or "(whole answer)"


@functools.cache
def _field_names(schema: type[BaseModel]) -> frozenset[str]:
    """Every property name in ``schema``'s JSON schema, nested models included."""
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                names.update(properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema.model_json_schema())
    return frozenset(names)


# Provider errors


def is_transient(error: BaseException) -> bool:
    """Whether ``error`` is a rate limit, timeout (or 408), connection failure or 5xx.

    Reads the status code (``status_code`` on openai and groq errors, ``code`` on
    google-genai's) or the error type, on the error and then on its ``__cause__`` chain,
    since langchain integrations re-raise provider errors as their own (``raise ... from``).
    """
    for link in _chain(error):
        verdict = _verdict(link)
        if verdict is not None:
            return verdict
    return False


def _chain(error: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    link: BaseException | None = error
    while link is not None and id(link) not in seen and len(seen) < _CHAIN_DEPTH:
        seen.add(id(link))
        yield link
        link = link.__cause__


def _verdict(error: BaseException) -> bool | None:
    status = _status(error)
    if status is not None:
        return status in (408, 429) or 500 <= status <= 599
    if isinstance(error, _transport_errors()):
        return True
    if isinstance(error, ModelError):
        if error.is_retryable:
            return True
        if isinstance(error, _NOT_RETRYABLE):
            return False
    return None


def _status(error: BaseException) -> int | None:
    status_types, google_type = _status_errors()
    if isinstance(error, status_types):
        code = getattr(error, "status_code", None)
    elif isinstance(error, google_type):
        code = getattr(error, "code", None)
    else:
        return None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


@functools.cache
def _status_errors() -> tuple[tuple[type[BaseException], ...], type[BaseException]]:
    import groq
    import openai
    from google.genai import errors as google_errors

    return (openai.APIStatusError, groq.APIStatusError), google_errors.APIError


@functools.cache
def _transport_errors() -> tuple[type[BaseException], ...]:
    import groq
    import httpx
    import openai

    return (
        TimeoutError,
        ConnectionError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
        openai.APIConnectionError,  # APITimeoutError too
        groq.APIConnectionError,
    )
