"""The shared structured-call helper: validation, the retry budget and error classes.

Provider exceptions are built offline from the real client classes; no request is sent.
"""

import json
import random

import groq
import httpx
import openai
import pytest
from google.genai import errors as google_errors
from helpers import FAKE_SUMMARY, FakeAnswersExhausted, FakeChatModel
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import chat_models as google_chat
from langchain_openai.chat_models import base as openai_chat

from call_center import llm_call
from call_center.llm_call import LLMCallError, invoke_structured, invoke_structured_counted
from call_center.models import Summary

SECRET = "Biscuit ZX-7781"
MESSAGES = [SystemMessage(content="system"), HumanMessage(content="<transcript>\n</transcript>")]
VALID = dict(FAKE_SUMMARY)
NO_PURPOSE = {k: v for k, v in FAKE_SUMMARY.items() if k != "call_purpose"}

_OPENAI_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
_GROQ_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
_GOOGLE_REQUEST = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta")


def _status(cls, status: int, request: httpx.Request = _OPENAI_REQUEST):
    return cls(
        f"provider said: {SECRET}", response=httpx.Response(status, request=request), body=None
    )


def _google(cls, code: int):
    return cls(code, {"error": {"code": code, "message": SECRET, "status": "X"}})


def _caused(wrapper: Exception, cause: Exception) -> Exception:
    """``wrapper`` as langchain raises it: ``raise wrapper from cause``."""
    try:
        raise wrapper from cause
    except Exception as error:
        return error


def _fake(*answers) -> FakeChatModel:
    fake = FakeChatModel()
    fake.outputs = list(answers)
    return fake


def _rate_limit():
    return _status(openai.RateLimitError, 429)


def _call(fake: FakeChatModel, provider: str = "openai"):
    return invoke_structured_counted(fake, provider, Summary, MESSAGES)


# The matrix, at helper level


def test_first_valid_answer_is_one_call(backoff_sleeps):
    fake = _fake(VALID)
    assert _call(fake) == (Summary.model_validate(VALID), 1)
    assert fake.calls == [MESSAGES]
    assert backoff_sleeps == []


def test_invoke_structured_returns_the_instance():
    assert invoke_structured(_fake(VALID), "openai", Summary, MESSAGES) == Summary.model_validate(
        VALID
    )


def test_pydantic_answer_is_validated_too():
    assert _call(_fake(Summary.model_validate(VALID)), "groq")[0] == Summary.model_validate(VALID)


def test_one_invalid_then_valid_retries_with_a_correction(backoff_sleeps):
    bad = {**VALID, "call_purpose": None, SECRET: SECRET}
    fake = _fake(bad, VALID)
    assert _call(fake) == (Summary.model_validate(VALID), 2)
    first, second = fake.calls
    assert first == MESSAGES
    assert second[:2] == MESSAGES and len(second) == 3
    correction = second[2]
    assert isinstance(correction, HumanMessage)
    assert "call_purpose: string_type" in correction.content
    assert "<unexpected field>: extra_forbidden" in correction.content
    assert SECRET not in correction.content and "Biscuit" not in correction.content
    assert backoff_sleeps == []


def test_correction_names_nested_paths():
    bad = {**VALID, "sentiment_trajectory": {"opening": "angry", "middle": "neutral"}}
    fake = _fake(bad, VALID)
    _call(fake)
    content = fake.calls[1][2].content
    assert "sentiment_trajectory.opening: literal_error" in content
    assert "sentiment_trajectory.closing: missing" in content


@pytest.mark.parametrize(
    "bad",
    [
        OutputParserException(f"Invalid json output: {SECRET}"),
        json.JSONDecodeError(f"bad {SECRET}", f"{{{SECRET}", 0),
        f"Sure! {SECRET}",
        None,
    ],
    ids=["parser", "json", "text", "none"],
)
def test_unparseable_answer_gets_a_correction_without_its_text(bad):
    fake = _fake(bad, VALID)
    assert _call(fake)[1] == 2
    content = fake.calls[1][2].content
    assert SECRET not in content and "Biscuit" not in content


def test_invalid_twice_fails_after_two_calls(backoff_sleeps):
    fake = _fake(NO_PURPOSE, NO_PURPOSE, VALID)
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    error = caught.value
    assert (error.kind, error.provider, error.attempts) == ("invalid_output", "openai", 2)
    assert error.error_class == "ValidationError"
    assert len(fake.calls) == 2
    assert backoff_sleeps == []


def test_rate_limit_then_valid_backs_off_two_seconds(backoff_sleeps):
    fake = _fake(_rate_limit(), VALID)
    assert _call(fake) == (Summary.model_validate(VALID), 2)
    assert backoff_sleeps == [2.0]
    assert fake.calls == [MESSAGES, MESSAGES]  # no correction for a provider error


def test_transient_three_times_fails_with_the_last_class(backoff_sleeps):
    fake = _fake(
        openai.APITimeoutError(request=_OPENAI_REQUEST),
        _status(openai.InternalServerError, 503),
        openai.APIConnectionError(request=_OPENAI_REQUEST),
        VALID,
    )
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    error = caught.value
    assert (error.kind, error.error_class, error.attempts) == (
        "provider_error",
        "APIConnectionError",
        3,
    )
    assert len(fake.calls) == 3
    assert backoff_sleeps == [2.0, 4.0]


def test_transient_then_invalid_twice_fails_as_invalid_after_three(backoff_sleeps):
    fake = _fake(_rate_limit(), NO_PURPOSE, NO_PURPOSE, VALID)
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    assert (caught.value.kind, caught.value.attempts) == ("invalid_output", 3)
    assert backoff_sleeps == [2.0]


def test_invalid_then_transient_keeps_the_correction(backoff_sleeps):
    fake = _fake(NO_PURPOSE, _rate_limit(), VALID)
    assert _call(fake)[1] == 3
    assert len(fake.calls[1]) == len(fake.calls[2]) == 3
    assert fake.calls[1][2] == fake.calls[2][2]
    assert backoff_sleeps == [2.0]


def test_transient_twice_then_invalid_has_no_call_left(backoff_sleeps):
    fake = _fake(_rate_limit(), _rate_limit(), NO_PURPOSE, VALID)
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    assert (caught.value.kind, caught.value.attempts) == ("invalid_output", 3)
    assert len(fake.calls) == 3


def test_invalid_then_transient_twice_fails_as_provider_error(backoff_sleeps):
    fake = _fake(NO_PURPOSE, _rate_limit(), _rate_limit(), VALID)
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    assert (caught.value.kind, caught.value.error_class, caught.value.attempts) == (
        "provider_error",
        "RateLimitError",
        3,
    )
    assert backoff_sleeps == [2.0]


def test_non_transient_error_fails_at_once(backoff_sleeps):
    fake = _fake(_status(openai.AuthenticationError, 401), VALID)
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    assert (caught.value.kind, caught.value.error_class, caught.value.attempts) == (
        "provider_error",
        "AuthenticationError",
        1,
    )
    assert len(fake.calls) == 1
    assert backoff_sleeps == []


def test_error_holds_no_provider_text():
    fake = _fake(_status(openai.BadRequestError, 400))
    with pytest.raises(LLMCallError) as caught:
        _call(fake)
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_call_past_the_fake_answers_fails_the_test():
    fake = _fake(TimeoutError(SECRET))
    with pytest.raises(FakeAnswersExhausted):
        _call(fake)
    assert len(fake.calls) == 2


def test_default_sleep_is_patched_in_tests(backoff_sleeps):
    llm_call.sleep(2.0)
    assert backoff_sleeps == [2.0]


# Each provider's errors

TRANSIENT = {
    # openai
    "openai-429": _status(openai.RateLimitError, 429),
    "openai-timeout": openai.APITimeoutError(request=_OPENAI_REQUEST),
    "openai-connection": openai.APIConnectionError(request=_OPENAI_REQUEST),
    "openai-408": _status(openai.APIStatusError, 408),
    "openai-500": _status(openai.InternalServerError, 500),
    "openai-503": _status(openai.APIStatusError, 503),
    "langchain-openai-429": _status(openai_chat.OpenAIRateLimitError, 429),
    "langchain-openai-timeout": openai_chat.OpenAITimeoutError(request=_OPENAI_REQUEST),
    "langchain-openai-5xx": _status(openai_chat.OpenAIAPIError, 502),
    # groq
    "groq-429": _status(groq.RateLimitError, 429, _GROQ_REQUEST),
    "groq-timeout": groq.APITimeoutError(request=_GROQ_REQUEST),
    "groq-connection": groq.APIConnectionError(request=_GROQ_REQUEST),
    "groq-408": _status(groq.APIStatusError, 408, _GROQ_REQUEST),
    "groq-500": _status(groq.InternalServerError, 500, _GROQ_REQUEST),
    "groq-503": _status(groq.APIStatusError, 503, _GROQ_REQUEST),
    # google-genai, raw and as langchain-google-genai re-raises it
    "gemini-429": _google(google_errors.ClientError, 429),
    "gemini-408": _google(google_errors.ClientError, 408),
    "gemini-500": _google(google_errors.ServerError, 500),
    "gemini-503": _google(google_errors.ServerError, 503),
    "gemini-timeout": httpx.ReadTimeout(SECRET, request=_GOOGLE_REQUEST),
    "gemini-connect": httpx.ConnectError(SECRET, request=_GOOGLE_REQUEST),
    "langchain-gemini-429": _caused(
        google_chat.GoogleRateLimitError(SECRET), _google(google_errors.ClientError, 429)
    ),
    "langchain-gemini-503": _caused(
        _google(google_chat.GoogleAPIError, 503), _google(google_errors.ServerError, 503)
    ),
    "langchain-gemini-wrapped-429": _caused(
        google_chat.ChatGoogleGenerativeAIError(SECRET), _google(google_errors.ClientError, 429)
    ),
    # plain Python and httpx
    "timeout": TimeoutError(SECRET),
    "connection-reset": ConnectionResetError(SECRET),
    "httpx-pool-timeout": httpx.PoolTimeout(SECRET),
    "httpx-remote-protocol": httpx.RemoteProtocolError(SECRET),
}

NOT_TRANSIENT = {
    "openai-401": _status(openai.AuthenticationError, 401),
    "openai-400": _status(openai.BadRequestError, 400),
    "openai-403": _status(openai.PermissionDeniedError, 403),
    "openai-404": _status(openai.NotFoundError, 404),
    "langchain-openai-401": _status(openai_chat.OpenAIAuthenticationError, 401),
    "groq-401": _status(groq.AuthenticationError, 401, _GROQ_REQUEST),
    "groq-400": _status(groq.BadRequestError, 400, _GROQ_REQUEST),
    "gemini-401": _google(google_errors.ClientError, 401),
    "gemini-400": _google(google_errors.ClientError, 400),
    "langchain-gemini-401": _caused(
        google_chat.GoogleAuthenticationError(SECRET), _google(google_errors.ClientError, 401)
    ),
    "langchain-gemini-wrapped-400": _caused(
        google_chat.ChatGoogleGenerativeAIError(SECRET), _google(google_errors.ClientError, 400)
    ),
    "value-error": ValueError(SECRET),
    "runtime-error": RuntimeError(SECRET),
    "unsupported-protocol": httpx.UnsupportedProtocol(SECRET),
}


@pytest.mark.parametrize("error", TRANSIENT.values(), ids=TRANSIENT.keys())
def test_transient_errors_are_recognised(error):
    assert llm_call.is_transient(error)


@pytest.mark.parametrize("error", NOT_TRANSIENT.values(), ids=NOT_TRANSIENT.keys())
def test_other_errors_are_not_transient(error):
    assert not llm_call.is_transient(error)


@pytest.mark.parametrize("provider", ["openai", "gemini", "groq"])
@pytest.mark.parametrize(
    ("errors", "retried"),
    [
        ((TRANSIENT["openai-429"], TRANSIENT["groq-429"], TRANSIENT["gemini-429"]), True),
        (
            (TRANSIENT["openai-timeout"], TRANSIENT["groq-timeout"], TRANSIENT["gemini-timeout"]),
            True,
        ),
        ((TRANSIENT["openai-500"], TRANSIENT["groq-500"], TRANSIENT["gemini-503"]), True),
        (
            (NOT_TRANSIENT["openai-401"], NOT_TRANSIENT["groq-401"], NOT_TRANSIENT["gemini-401"]),
            False,
        ),
    ],
    ids=["429", "timeout", "5xx", "401"],
)
def test_each_provider_is_classified_the_same_way(provider, errors, retried, backoff_sleeps):
    error = dict(zip(["openai", "groq", "gemini"], errors, strict=True))[provider]
    fake = _fake(error, VALID)
    if retried:
        assert _call(fake, provider)[1] == 2
        assert backoff_sleeps == [2.0]
    else:
        with pytest.raises(LLMCallError) as caught:
            _call(fake, provider)
        assert (caught.value.provider, caught.value.attempts) == (provider, 1)


def test_cause_cycle_terminates():
    a, b = ValueError("a"), ValueError("b")
    a.__cause__, b.__cause__ = b, a
    assert not llm_call.is_transient(a)


# The budget, over random sequences


def _random_answer(rng: random.Random):
    return rng.choice(
        [
            lambda: VALID,
            lambda: NO_PURPOSE,
            lambda: {**VALID, SECRET: SECRET},
            lambda: f"text {SECRET}",
            lambda: OutputParserException(SECRET),
            lambda: _status(openai.RateLimitError, 429),
            lambda: _status(groq.InternalServerError, 503, _GROQ_REQUEST),
            lambda: _google(google_errors.ClientError, 429),
            lambda: httpx.ReadTimeout(SECRET),
            lambda: _status(openai.AuthenticationError, 401),
            lambda: _google(google_errors.ClientError, 400),
            lambda: RuntimeError(SECRET),
        ]
    )()


@pytest.mark.parametrize("seed", range(200))
def test_budget_holds_for_any_sequence(seed, backoff_sleeps):
    rng = random.Random(seed)
    fake = _fake(*[_random_answer(rng) for _ in range(6)])
    try:
        value, attempts = _call(fake, rng.choice(["openai", "gemini", "groq"]))
    except LLMCallError as error:
        assert 1 <= error.attempts == len(fake.calls) <= llm_call.MAX_CALLS
        assert SECRET not in str(error) and SECRET not in error.error_class
    else:
        assert isinstance(value, Summary)
        assert attempts == len(fake.calls) <= llm_call.MAX_CALLS
    assert len(fake.calls) <= llm_call.MAX_CALLS
    assert len(backoff_sleeps) <= 2 and backoff_sleeps == [2.0, 4.0][: len(backoff_sleeps)]
    for messages in fake.calls:
        assert messages[:2] == MESSAGES and len(messages) <= 3
        assert all(SECRET not in m.content for m in messages[2:])
