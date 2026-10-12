"""Chat model factory: one LangChain chat model for the configured provider.

``get_chat_model`` is the single seam the LLM stages call, so tests replace it with a
fake (``tests/conftest.py``) and no test reaches a real provider. Only OpenAI is wired in
this story; Gemini and Groq raise ``ProviderNotSupportedError`` until story 4.2.

Each request times out after ``REQUEST_TIMEOUT_S`` and the client never retries on its
own (``max_retries=0``); the retry policy belongs to the stages (story 4.3).
"""

from langchain_core.language_models import BaseChatModel

from call_center.config import Settings, env_names

REQUEST_TIMEOUT_S = 60


class LLMConfigError(Exception):
    """The selected provider cannot be used as configured. Messages never hold a value."""


class MissingAPIKeyError(LLMConfigError):
    def __init__(self, provider: str, key_field: str) -> None:
        self.provider = provider
        names = " / ".join(env_names(key_field))
        super().__init__(f"{provider} API key missing (set {names})")


class ProviderNotSupportedError(LLMConfigError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"{provider} is not supported yet")


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


def get_chat_model(settings: Settings) -> BaseChatModel:
    """The chat model for ``settings.llm_provider``; raises ``LLMConfigError``."""
    if settings.llm_provider == "openai":
        return _openai(settings)
    raise ProviderNotSupportedError(settings.llm_provider)


def model_name(settings: Settings) -> str:
    """The model id configured for the selected provider."""
    return getattr(settings, f"{settings.llm_provider}_model")
