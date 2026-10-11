"""Package structure tests for WI-1 acceptance criteria."""

import importlib
import pathlib
import subprocess
import sys
import tomllib


def test_gitweave_importable() -> None:
    importlib.import_module("gitweave")
    from gitweave.cli import main  # noqa: F401


def test_gw_help_exits_zero() -> None:
    result = subprocess.run(
        ["python3", "-m", "gitweave.cli", "--help"],
        capture_output=True,
    )
    assert result.returncode == 0


def test_gw_help_lists_verbs() -> None:
    result = subprocess.run(
        ["python3", "-m", "gitweave.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    for verb in ("plan", "apply", "reset"):
        assert verb in output, f"verb {verb!r} not in --help output"


def test_pyproject_declares_gw_entrypoint() -> None:
    data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
    assert data["project"]["scripts"]["gw"] == "gitweave.cli:main"
