"""Shared fixtures: folder markers, config isolation and the fake ASR and chat model.

Tests never reach a real ASR model unless marked ``slow``, and never a real LLM unless
marked ``live`` (opt in with ``-m live``; such tests also read the real ``.env``).
"""

from pathlib import Path

import pytest
from helpers import FakeChatModel

# The LLM-stage guard fixture, for tests in every folder.
from security.llm_guard import llm_guard  # noqa: F401

_MARKERS = ("unit", "integration", "security")
_TESTS_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        parts = Path(item.path).relative_to(_TESTS_ROOT).parts
        for marker in _MARKERS:
            if marker in parts:
                item.add_marker(getattr(pytest.mark, marker))
    # A command-line -m replaces addopts' "not slow and not live", so keep real-model and
    # real-LLM tests out of any selection that does not name them (e.g. -m integration).
    markexpr = config.getoption("markexpr") or ""
    for opt_in in ("slow", "live"):
        if opt_in not in markexpr:
            chosen = [item for item in items if item.get_closest_marker(opt_in)]
            if chosen:
                items[:] = [item for item in items if not item.get_closest_marker(opt_in)]
                config.hook.pytest_deselected(items=chosen)


@pytest.fixture(autouse=True)
def _isolated_config(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of the developer's shell and real ``.env``.

    Lifted only for ``live`` tests, which need the real key from the shell or ``.env``.
    """
    if request.node.get_closest_marker("live"):
        return
    from call_center.config import ENV_VARS, Settings

    # setenv then delenv records each name, so anything a test (or the CLI) writes to
    # os.environ is undone afterwards, even for names that were not set before.
    # Also the variables that would switch Gemini to Vertex AI.
    for name in (*ENV_VARS, "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE"):
        for variant in (name, name.lower()):
            monkeypatch.setenv(variant, "")
            monkeypatch.delenv(variant)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def _isolated_transcript_cache(
    _isolated_config: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the transcript cache under ``tmp_path`` so no test writes to the repo."""
    cache_dir = tmp_path / "transcript-cache"
    monkeypatch.setenv("TRANSCRIPT_CACHE_DIR", str(cache_dir))
    return cache_dir


class _SilentTranscriber:
    """Fake ASR that hears no speech; tests needing segments patch their own."""

    def transcribe(self, path):
        return []


@pytest.fixture(autouse=True)
def _fake_transcriber(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never load a real ASR model unless the test is marked ``slow``."""
    if request.node.get_closest_marker("slow"):
        return
    from call_center import asr

    monkeypatch.setattr(asr, "get_transcriber", lambda model_size: _SilentTranscriber())


@pytest.fixture(autouse=True)
def fake_chat_model(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> FakeChatModel:
    """Every ``llm.get_chat_model`` call returns this fake unless the test is ``live``."""
    fake = FakeChatModel()
    if request.node.get_closest_marker("live"):
        return fake
    from call_center import llm

    def get_chat_model(settings):
        fake.settings.append(settings)
        return fake

    monkeypatch.setattr(llm, "get_chat_model", get_chat_model)
    return fake
