"""The chat model factory. Builds clients only; no test sends a request."""

import pytest
from langchain_openai import ChatOpenAI

from call_center import llm
from call_center.config import load_settings

# Bound at import, before the autouse fake replaces ``llm.get_chat_model``.
from call_center.llm import get_chat_model as real_get_chat_model

KEY = "sk-test-not-a-real-key-0123456789"


def test_autouse_fake_replaces_the_factory(fake_chat_model):
    assert llm.get_chat_model(load_settings()) is fake_chat_model
    assert real_get_chat_model is not llm.get_chat_model


def test_openai_client_is_configured_from_settings():
    model = real_get_chat_model(load_settings(openai_api_key=KEY, openai_model="gpt-4o-mini"))
    assert type(model) is ChatOpenAI
    assert model.model_name == "gpt-4o-mini"
    assert model.request_timeout == llm.REQUEST_TIMEOUT_S == 60
    assert model.max_retries == 0
    assert model.openai_api_key.get_secret_value() == KEY


def test_openai_default_model_is_gpt_4o():
    assert real_get_chat_model(load_settings(openai_api_key=KEY)).model_name == "gpt-4o"


def test_openai_key_is_passed_explicitly_not_read_from_os_environ(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environ")
    model = real_get_chat_model(load_settings(openai_api_key=KEY))
    assert model.openai_api_key.get_secret_value() == KEY


def test_missing_openai_key_names_the_provider_and_variable():
    with pytest.raises(llm.MissingAPIKeyError) as caught:
        real_get_chat_model(load_settings())
    message = str(caught.value)
    assert "openai" in message
    assert "OPENAI_API_KEY" in message
    assert isinstance(caught.value, llm.LLMConfigError)


def test_missing_key_message_never_holds_a_key_value(monkeypatch):
    # A Gemini key is set, but the OpenAI one is missing: no value may appear.
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    with pytest.raises(llm.MissingAPIKeyError) as caught:
        real_get_chat_model(load_settings())
    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value)


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_other_providers_are_not_supported_yet(provider):
    settings = load_settings(llm_provider=provider, gemini_api_key=KEY, groq_api_key=KEY)
    with pytest.raises(llm.ProviderNotSupportedError, match=f"{provider} is not supported yet"):
        real_get_chat_model(settings)


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "gpt-4o"), ("gemini", "gemini-2.0-flash"), ("groq", "llama-3.3-70b-versatile")],
)
def test_model_name_follows_the_provider(provider, model):
    assert llm.model_name(load_settings(llm_provider=provider)) == model
