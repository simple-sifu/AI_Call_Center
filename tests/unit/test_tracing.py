import os

import pytest
from langsmith import utils as ls_utils

from call_center.config import Settings
from call_center.tracing import TRACING_FLAGS, configure_tracing

FLAGS = ("LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING")


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def _langsmith_enabled() -> bool:
    """What langsmith itself decides from os.environ (its lookup is cached)."""
    ls_utils.get_env_var.cache_clear()
    return ls_utils.tracing_is_enabled() is True


@pytest.fixture(autouse=True)
def _fresh_langsmith_cache():
    ls_utils.get_env_var.cache_clear()
    yield
    ls_utils.get_env_var.cache_clear()


def test_tracing_flags_cover_every_name_langsmith_reads():
    assert set(TRACING_FLAGS) == set(FLAGS)


def test_off_by_default_and_forced_off():
    env = {"LANGCHAIN_TRACING_V2": "true"}
    assert configure_tracing(_settings(), env) is False
    assert env == dict.fromkeys(FLAGS, "false")


def test_on_with_flag_and_key_exports_settings():
    env: dict[str, str] = {}
    settings = _settings(
        langsmith_tracing=True, langsmith_api_key="ls-test-key", langsmith_project="calls"
    )
    assert configure_tracing(settings, env) is True
    assert env == {
        **dict.fromkeys(FLAGS, "true"),
        "LANGSMITH_API_KEY": "ls-test-key",
        "LANGSMITH_PROJECT": "calls",
    }


def test_project_is_optional():
    env: dict[str, str] = {}
    assert configure_tracing(_settings(langsmith_tracing=True, langsmith_api_key="k"), env)
    assert "LANGSMITH_PROJECT" not in env


def test_requested_without_key_warns_and_stays_off(capsys):
    env: dict[str, str] = {}
    assert configure_tracing(_settings(langsmith_tracing=True), env) is False
    assert env["LANGSMITH_TRACING"] == "false"
    assert "tracing requested but no API key" in capsys.readouterr().err


def test_key_without_flag_stays_off(capsys):
    env: dict[str, str] = {}
    assert configure_tracing(_settings(langsmith_api_key="k"), env) is False
    assert env["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in env
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("flag", FLAGS)
def test_any_flag_name_without_key_is_effectively_off(monkeypatch, capsys, flag):
    monkeypatch.setenv(flag, "true")
    assert configure_tracing(Settings(_env_file=None)) is False
    assert not _langsmith_enabled()
    assert "tracing requested but no API key" in capsys.readouterr().err


def test_on_wins_over_a_conflicting_legacy_false(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    settings = Settings(_env_file=None)
    assert configure_tracing(settings) is _langsmith_enabled() is settings.langsmith_tracing
    assert os.environ["LANGCHAIN_TRACING_V2"] == os.environ["LANGSMITH_TRACING"]
