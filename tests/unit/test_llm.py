"""The chat model factory. Builds clients only; no test sends a request."""

import logging
import os
from typing import get_args

import pytest
from google.genai import _api_client as genai_api_client
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from call_center import llm
from call_center.config import LLMProvider, load_settings

# Bound at import, before the autouse fake replaces ``llm.get_chat_model``.
from call_center.llm import get_chat_model as real_get_chat_model
from call_center.models import Summary

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


# Gemini


def test_gemini_client_is_configured_from_settings():
    model = real_get_chat_model(load_settings(llm_provider="gemini", gemini_api_key=KEY))
    assert type(model) is ChatGoogleGenerativeAI
    assert model.model == "gemini-2.0-flash"
    assert model.timeout == llm.REQUEST_TIMEOUT_S
    assert model.google_api_key.get_secret_value() == KEY


def test_gemini_client_makes_exactly_one_attempt():
    model = real_get_chat_model(load_settings(llm_provider="gemini", gemini_api_key=KEY))
    # The request the client would send (built locally, not sent) and the retry policy
    # google-genai derives from it.
    config = model._prepare_request([HumanMessage(content="hi")])["config"]
    retry_options = config.http_options.retry_options
    assert retry_options.attempts == 1
    assert genai_api_client.retry_args(retry_options)["stop"].max_attempt_number == 1
    assert config.http_options.timeout == llm.REQUEST_TIMEOUT_S * 1000


@pytest.mark.parametrize("name", ["GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE"])
def test_gemini_ignores_the_vertex_ai_switch(monkeypatch, name):
    monkeypatch.setenv(name, "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "other-key-from-environ")
    model = real_get_chat_model(load_settings(llm_provider="gemini", gemini_api_key=KEY))
    assert model._use_vertexai is False
    api_client = model.client._api_client
    assert not api_client.vertexai  # None: google-genai's Gemini API backend
    assert "generativelanguage.googleapis.com" in api_client._http_options.base_url
    assert api_client.api_key == KEY
    assert os.environ[name] == "true"  # restored after the build


def test_gemini_structured_output_writes_nothing_to_stderr(capfd, caplog):
    model = real_get_chat_model(load_settings(llm_provider="gemini", gemini_api_key=KEY))
    with caplog.at_level(logging.WARNING):
        model.with_structured_output(**llm.structured_output_args("gemini", Summary))
    assert capfd.readouterr().err == ""
    assert caplog.records == []


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_gemini_key_is_read_from_either_variable(monkeypatch, name):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv(name, KEY)
    model = real_get_chat_model(load_settings())
    assert type(model) is ChatGoogleGenerativeAI
    assert model.google_api_key.get_secret_value() == KEY


def test_gemini_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-x")
    model = real_get_chat_model(load_settings(llm_provider="gemini", gemini_api_key=KEY))
    assert model.model == "gemini-x"


# Groq


def test_groq_client_is_configured_from_settings():
    model = real_get_chat_model(load_settings(llm_provider="groq", groq_api_key=KEY))
    assert type(model) is ChatGroq
    assert model.model_name == "llama-3.3-70b-versatile"
    assert model.request_timeout == llm.REQUEST_TIMEOUT_S
    assert model.max_retries == 0
    assert model.groq_api_key.get_secret_value() == KEY


def test_groq_key_is_read_from_its_variable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    assert real_get_chat_model(load_settings()).groq_api_key.get_secret_value() == KEY


def test_groq_model_override(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "groq-y")
    model = real_get_chat_model(load_settings(llm_provider="groq", groq_api_key=KEY))
    assert model.model_name == "groq-y"


@pytest.mark.parametrize(
    ("provider", "names"),
    [("gemini", "GEMINI_API_KEY / GOOGLE_API_KEY"), ("groq", "GROQ_API_KEY")],
)
def test_missing_key_names_the_provider_and_its_variables(monkeypatch, provider, names):
    # Only another provider's key is set: no fallback to it, and its value never appears.
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    with pytest.raises(llm.MissingAPIKeyError) as caught:
        real_get_chat_model(load_settings(llm_provider=provider))
    assert str(caught.value) == f"{provider} API key missing (set {names})"
    assert caught.value.provider == provider
    assert KEY not in str(caught.value) and KEY not in repr(caught.value)


def test_every_provider_is_built():
    settings = dict(openai_api_key=KEY, gemini_api_key=KEY, groq_api_key=KEY)
    for provider in get_args(LLMProvider):
        real_get_chat_model(load_settings(llm_provider=provider, **settings))
    assert not hasattr(llm, "ProviderNotSupportedError")


# Structured output


def test_openai_asks_for_the_json_schema():
    assert llm.structured_output_args("openai", Summary) == {
        "schema": Summary.model_json_schema(),
        "method": "json_schema",
    }


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_gemini_and_groq_use_tool_calling_with_the_class(provider):
    assert llm.structured_output_args(provider, Summary) == {
        "schema": Summary,
        "method": "function_calling",
    }


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_real_clients_accept_tool_calling_structured_output(provider):
    settings = load_settings(llm_provider=provider, gemini_api_key=KEY, groq_api_key=KEY)
    model = real_get_chat_model(settings)
    # Builds the runnable only; nothing is invoked.
    assert model.with_structured_output(**llm.structured_output_args(provider, Summary))


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "gpt-4o"), ("gemini", "gemini-2.0-flash"), ("groq", "llama-3.3-70b-versatile")],
)
def test_model_name_follows_the_provider(provider, model):
    assert llm.model_name(load_settings(llm_provider=provider)) == model
