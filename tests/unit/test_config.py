from pathlib import Path

import pytest
from pydantic import ValidationError

from call_center.config import Settings, format_config_error


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
    assert s.whisper_model_size == "tiny"
    assert (s.openai_model, s.gemini_model, s.groq_model) == (
        "gpt-4o",
        "gemini-2.0-flash",
        "llama-3.3-70b-versatile",
    )
    assert s.openai_api_key is None
    assert s.gemini_api_key is None
    assert s.groq_api_key is None
    assert s.langsmith_api_key is None
    assert s.langsmith_project is None
    assert s.langsmith_tracing is False


def test_report_output_dir_default(monkeypatch):
    monkeypatch.delenv("REPORT_OUTPUT_DIR", raising=False)
    assert Settings(_env_file=None).report_output_dir == Path("reports")


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "small")
    s = Settings(_env_file=None)
    assert (s.llm_provider, s.whisper_model_size) == ("groq", "small")


def test_legacy_tracing_names(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "p")
    s = Settings(_env_file=None)
    assert s.langsmith_tracing is True
    assert s.langsmith_api_key.get_secret_value() == "k"
    assert s.langsmith_project == "p"


def test_langsmith_names(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "k2")
    s = Settings(_env_file=None)
    assert s.langsmith_tracing is True
    assert s.langsmith_api_key.get_secret_value() == "k2"


def test_google_api_key_alias(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    s = Settings(_env_file=None)
    assert s.gemini_api_key.get_secret_value() == "g-key"


def test_secret_hygiene(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    s = Settings(_env_file=None)
    assert s.openai_api_key.get_secret_value() == "sk-test-123"
    assert "sk-test-123" not in repr(s)
    assert "sk-test-123" not in str(s)


def test_secret_not_in_error_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("LLM_PROVIDER", "sk-test-123")
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None)
    message = format_config_error(info.value)
    assert "sk-test-123" not in message
    assert "LLM_PROVIDER" in message


def test_unknown_vars_ignored(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "x")
    Settings(_env_file=None)


def test_env_file_read_when_passed(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=gemini\nOPENAI_MODEL=gpt-4o-mini\nSERPAPI_API_KEY=x\n")
    s = Settings(_env_file=env)
    assert s.llm_provider == "gemini"
    assert s.openai_model == "gpt-4o-mini"


def test_empty_values_fall_back_to_defaults(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_MODEL=\nLANGCHAIN_TRACING_V2=\n")
    s = Settings(_env_file=env)
    assert s.openai_model == "gpt-4o"
    assert s.langsmith_tracing is False
