"""Auto-apply the unit/integration/security marker from each test's folder."""

from pathlib import Path

import pytest

_MARKERS = ("unit", "integration", "security")
_TESTS_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = Path(item.path).relative_to(_TESTS_ROOT).parts
        for marker in _MARKERS:
            if marker in parts:
                item.add_marker(getattr(pytest.mark, marker))


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
