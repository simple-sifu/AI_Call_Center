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
