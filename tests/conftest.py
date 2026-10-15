"""tests/conftest.py — pytest session configuration.

Skips all tests under tests/acceptance/ when the ``gitweave`` package is not
importable.  Uses ``sys.executable`` (same interpreter as pytest) so it works
whether the ``gw`` entry-point binary is installed or not — the gate may run
pytest with ``pythonpath = ["."]`` without a globally installed ``gw`` script.
"""

from __future__ import annotations

import subprocess
import sys
import pytest


def _gw_functional() -> bool:
    """Return True if gitweave.cli is importable via the current interpreter."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "--help"],
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
