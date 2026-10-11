"""Auto-apply the unit/integration/security marker from each test's folder."""

from pathlib import Path

import pytest

_MARKERS = ("unit", "integration", "security")
_TESTS_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        parts = Path(item.path).relative_to(_TESTS_ROOT).parts
        for marker in _MARKERS:
            if marker in parts:
                item.add_marker(getattr(pytest.mark, marker))
    # A command-line -m replaces addopts' "not slow", so keep real-model tests out of
    # any selection that does not name them (e.g. -m integration).
    if "slow" not in (config.getoption("markexpr") or ""):
        slow = [item for item in items if item.get_closest_marker("slow")]
        if slow:
            items[:] = [item for item in items if not item.get_closest_marker("slow")]
            config.hook.pytest_deselected(items=slow)


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of the developer's shell and real ``.env``."""
    from call_center.config import ENV_VARS, Settings

    # setenv then delenv records each name, so anything a test (or the CLI) writes to
    # os.environ is undone afterwards, even for names that were not set before.
    for name in ENV_VARS:
        for variant in (name, name.lower()):
            monkeypatch.setenv(variant, "")
            monkeypatch.delenv(variant)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


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
