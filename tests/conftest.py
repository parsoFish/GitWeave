"""tests/conftest.py — pytest session configuration.

Skips all tests under tests/acceptance/ when the ``gw`` CLI binary is not
functional (import failure, missing binary, etc.).  This guards against the
gate environment having live credentials set but an uninstalled package,
which would cause acceptance tests to *run* rather than skip and then fail
hard with ModuleNotFoundError.
"""

from __future__ import annotations

import subprocess
import pytest


def _gw_functional() -> bool:
    """Return True if the ``gw`` binary exits 0 on ``--help``."""
    try:
        result = subprocess.run(
            ["gw", "--help"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_GW_OK: bool = _gw_functional()
_SKIP_GW = pytest.mark.skip(
    reason="gw binary not functional (gitweave not installed); skipping acceptance tests"
)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Mark acceptance tests to skip when gw is not operational."""
    if _GW_OK:
        return
    for item in items:
        if "acceptance" in str(item.fspath):
            item.add_marker(_SKIP_GW)
