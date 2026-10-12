"""Chat model factory: one LangChain chat model for the configured provider.

``get_chat_model`` is the single seam the LLM stages call, so tests replace it with a
fake (``tests/conftest.py``) and no test reaches a real provider. OpenAI, Gemini and Groq
are built the same way: the key is passed explicitly from settings, so a key elsewhere in
``os.environ`` never replaces it, and a missing key raises ``MissingAPIKeyError``. The
client libraries still read some environment variables of their own: for example
``LANGSMITH_GATEWAY`` can point Gemini at a gateway base URL. Gemini is pinned to the
Gemini API, so ``GOOGLE_GENAI_USE_VERTEXAI`` / ``GOOGLE_GENAI_USE_ENTERPRISE`` cannot
switch it to Vertex AI.

Each request times out after ``REQUEST_TIMEOUT_S`` and the client makes one attempt with
no retries of its own; the retry policy belongs to the stages (story 4.3).

``structured_output_args`` says how each provider is asked for structured output: OpenAI
takes the JSON schema (``json_schema``); Gemini and Groq use tool calling with the
pydantic class, since they do not reliably accept that schema. Callers still validate
every answer.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from call_center.config import LLMProvider, Settings, env_names

REQUEST_TIMEOUT_S = 60

# Environment variables with which google-genai's ``Client`` picks Vertex AI on its own,
# even when langchain-google-genai was told ``vertexai=False``.
_GOOGLE_BACKEND_ENV = ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE")

# Gemini's tool-calling schema conversion warns, on every call, about JSON-schema keys it
# drops (``$defs``, ``additionalProperties``) to stderr, mixing library noise into the
# CLI's output. The stage validates every answer with the full schema anyway.
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)


class LLMConfigError(Exception):
    """The selected provider cannot be used as configured. Messages never hold a value."""


class MissingAPIKeyError(LLMConfigError):
    def __init__(self, provider: str, key_field: str) -> None:
        self.provider = provider
        names = " / ".join(env_names(key_field))
        super().__init__(f"{provider} API key missing (set {names})")


def _openai(settings: Settings) -> BaseChatModel:
    if settings.openai_api_key is None:
        raise MissingAPIKeyError("openai", "openai_api_key")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        timeout=REQUEST_TIMEOUT_S,
        max_retries=0,
    )


def _gemini(settings: Settings) -> BaseChatModel:
    if settings.gemini_api_key is None:
        raise MissingAPIKeyError("gemini", "gemini_api_key")
    from langchain_google_genai import ChatGoogleGenerativeAI

    with _without_env(_GOOGLE_BACKEND_ENV):
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            api_key=settings.gemini_api_key,
            timeout=REQUEST_TIMEOUT_S,
            # langchain-google-genai documents 1 as "one attempt, no retries"; 0 means
            # "use the Google default" (5 retries).
            max_retries=1,
            vertexai=False,
        )


@contextmanager
def _without_env(names: tuple[str, ...]) -> Iterator[None]:
    """Hide ``names`` from ``os.environ`` for the block, then restore them."""
    saved = {name: os.environ.pop(name) for name in names if name in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def _groq(settings: Settings) -> BaseChatModel:
    if settings.groq_api_key is None:
        raise MissingAPIKeyError("groq", "groq_api_key")
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        timeout=REQUEST_TIMEOUT_S,
        max_retries=0,
    )


_BUILDERS = {"openai": _openai, "gemini": _gemini, "groq": _groq}


def get_chat_model(settings: Settings) -> BaseChatModel:
    """The chat model for ``settings.llm_provider``; raises ``LLMConfigError``."""
    return _BUILDERS[settings.llm_provider](settings)


def structured_output_args(provider: LLMProvider, schema: type[BaseModel]) -> dict[str, Any]:
    """Keyword arguments for ``with_structured_output`` asking ``provider`` for ``schema``."""
    if provider == "openai":
        return {"schema": schema.model_json_schema(), "method": "json_schema"}
    return {"schema": schema, "method": "function_calling"}


def model_name(settings: Settings) -> str:
    """The model id configured for the selected provider."""
    return getattr(settings, f"{settings.llm_provider}_model")
