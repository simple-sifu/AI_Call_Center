"""Application settings loaded from the environment and ``.env``.

API keys are optional here; the provider factory (Epic 4) enforces the key for the
selected provider. Keys are ``SecretStr`` so they never appear in repr or errors.
"""

from typing import Literal, get_args

from pydantic import AliasChoices, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openai", "gemini", "groq"]
WhisperModelSize = Literal["tiny", "base", "small", "medium", "large-v3"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
        populate_by_name=True,
    )

    llm_provider: LLMProvider = Field("openai", validation_alias=AliasChoices("LLM_PROVIDER"))
    whisper_model_size: WhisperModelSize = Field(
        "tiny", validation_alias=AliasChoices("WHISPER_MODEL_SIZE")
    )

    openai_model: str = Field("gpt-4o", validation_alias=AliasChoices("OPENAI_MODEL"))
    gemini_model: str = Field("gemini-2.0-flash", validation_alias=AliasChoices("GEMINI_MODEL"))
    groq_model: str = Field("llama-3.3-70b-versatile", validation_alias=AliasChoices("GROQ_MODEL"))

    openai_api_key: SecretStr | None = Field(None, validation_alias=AliasChoices("OPENAI_API_KEY"))
    gemini_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    groq_api_key: SecretStr | None = Field(None, validation_alias=AliasChoices("GROQ_API_KEY"))

    langsmith_tracing: bool = Field(
        False, validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
    )
    langsmith_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
    )
    langsmith_project: str | None = Field(
        None, validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT")
    )


def env_names(field: str) -> list[str]:
    """Environment variable names accepted for a settings field."""
    alias = Settings.model_fields[field].validation_alias
    if isinstance(alias, AliasChoices):
        return [str(choice) for choice in alias.choices]
    return [field.upper()]


ENV_VARS: tuple[str, ...] = tuple(
    name for field in Settings.model_fields for name in env_names(field)
)


def load_settings(**overrides: object) -> Settings:
    """Load settings from the environment and ``.env``; raises ``ValidationError``."""
    return Settings(**overrides)


def format_config_error(error: ValidationError) -> str:
    """Name each bad variable and its allowed values without echoing the input."""
    problems = []
    for item in error.errors(include_input=False, include_url=False):
        loc = item["loc"][0] if item["loc"] else ""
        field = str(loc)
        if field not in Settings.model_fields:
            field = next(
                (f for f in Settings.model_fields if str(loc).upper() in env_names(f)), field
            )
        if field in Settings.model_fields:
            name = " / ".join(env_names(field))
            allowed = get_args(Settings.model_fields[field].annotation)
            if allowed and all(isinstance(a, str) for a in allowed):
                detail = "must be one of " + ", ".join(allowed)
            else:
                detail = _safe_msg(item)
        else:
            name, detail = field or "settings", _safe_msg(item)
        problems.append(f"{name} {detail}")
    return "; ".join(problems)


def _safe_msg(item: dict) -> str:
    # pydantic messages describe the expected type, not the received value.
    return str(item.get("msg", "is invalid")).lower()
