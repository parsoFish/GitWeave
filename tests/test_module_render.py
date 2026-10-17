"""Tests for gitweave.module_render — offline module rendering via Copier."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from gitweave.module_render import CopierVersionError, render_module


class TestModuleRender:
    """Unit + integration tests for render_module() and gw module render CLI."""

    # ------------------------------------------------------------------
    # AC1: non-default input value appears in rendered output
    # ------------------------------------------------------------------
    def test_render_non_default_input_appears_in_output(self) -> None:
        """Rendering python_service with a custom service_name embeds it in output."""
        with tempfile.TemporaryDirectory() as tmp:
            render_module(
                "python_service",
                tmp,
                data={"service_name": "acme_worker", "repo_name": "acme_worker"},
            )
            rendered_files = list(Path(tmp).rglob("*"))
            texts = [
                f.read_text()
                for f in rendered_files
                if f.is_file()
            ]
            assert any("acme_worker" in t for t in texts), (
                f"'acme_worker' not found in any rendered file; found files: "
                f"{[str(f) for f in rendered_files]}"
            )

    # ------------------------------------------------------------------
    # AC2: min_copier_version enforcement
    # ------------------------------------------------------------------
    def test_min_copier_version_enforced(self) -> None:
        """render_module raises CopierVersionError when installed copier < required."""
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "gitweave.module_render._installed_copier_version",
                return_value="0.0.1",
            ),
        ):
            with pytest.raises(CopierVersionError) as exc_info:
                render_module("python_service", tmp)
            msg = str(exc_info.value)
            assert "9.0.0" in msg, f"required version not in message: {msg}"
            assert "0.0.1" in msg, f"installed version not in message: {msg}"

    # ------------------------------------------------------------------
    # AC3: rendered CI workflow passes yamllint
    # ------------------------------------------------------------------
    def test_rendered_ci_workflow_passes_yamllint(self) -> None:
        """Rendered .github/workflows/ci.yml passes yamllint."""
        with tempfile.TemporaryDirectory() as tmp:
            render_module(
                "python_service",
                tmp,
                data={"service_name": "my_service", "repo_name": "my_service"},
            )
            workflow = Path(tmp) / ".github" / "workflows" / "ci.yml"
            assert workflow.exists(), f"CI workflow not rendered at {workflow}"
            result = subprocess.run(
                ["yamllint", "-d", "relaxed", str(workflow)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"yamllint failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

    # ------------------------------------------------------------------
    # module not found
    # ------------------------------------------------------------------
    def test_module_not_found_raises(self) -> None:
        """render_module raises FileNotFoundError for unknown module name."""
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError, match="nonexistent"):
                render_module("nonexistent", tmp)

    # ------------------------------------------------------------------
    # AC4: CLI help exits zero with module + render registered
    # ------------------------------------------------------------------
    def test_cli_module_render_help_exits_zero(self) -> None:
        """gw module render --help exits 0 and is registered in the CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "module", "render", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--help exited {result.returncode}:\n{result.stderr}"
        )
        assert "render" in result.stdout.lower(), (
            f"'render' not in help output:\n{result.stdout}"
        )
