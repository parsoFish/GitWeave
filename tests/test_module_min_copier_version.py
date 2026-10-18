"""Tests for min_copier_version enforcement in gw module render (K4b).

Real run: render_module with installed copier below module's min_copier_version
          exits non-zero (raises CopierVersionError) naming both versions and
          renders nothing.

Mutant run: patching _check_version to a no-op allows render to succeed,
            proving the enforcement gate is load-bearing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from gitweave.module_render import (
    CopierVersionError,
    _check_version,
    _installed_copier_version,
    render_module,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "min_ver_fixture"


class TestMinCopierVersionRealRun:
    """Enforcement fires: version below requirement raises CopierVersionError."""

    def test_check_version_raises_for_fixture(self) -> None:
        """_check_version raises CopierVersionError for fixture requiring 999.0.0."""
        with pytest.raises(CopierVersionError) as exc_info:
            _check_version(FIXTURE_DIR)
        msg = str(exc_info.value)
        assert "999.0.0" in msg, f"Required version not in error message: {msg!r}"
        installed = _installed_copier_version()
        assert installed in msg, f"Installed version {installed!r} not in error message: {msg!r}"

    def test_render_module_raises_when_below_min_version(self) -> None:
        """render_module raises CopierVersionError when installed copier < required."""
        with (
            patch(
                "gitweave.module_render._installed_copier_version",
                return_value="0.0.1",
            ),
            tempfile.TemporaryDirectory() as tmp,
        ):
            with pytest.raises(CopierVersionError) as exc_info:
                render_module("python_service", tmp)
            msg = str(exc_info.value)
            # python_service requires copier>=9.0.0; error must name both
            assert "9.0.0" in msg, f"Required version not in error: {msg!r}"
            assert "0.0.1" in msg, f"Installed version not in error: {msg!r}"

    def test_render_module_renders_nothing_on_version_error(self) -> None:
        """render_module renders nothing when CopierVersionError is raised."""
        with (
            patch(
                "gitweave.module_render._installed_copier_version",
                return_value="0.0.1",
            ),
            tempfile.TemporaryDirectory() as tmp,
        ):
            with pytest.raises(CopierVersionError):
                render_module("python_service", tmp)
            rendered = list(Path(tmp).rglob("*"))
            assert rendered == [], (
                f"Expected nothing rendered after version error; got: "
                f"{[str(f) for f in rendered]}"
            )


class TestMinCopierVersionMutantRun:
    """Mutation test: no-op enforcement allows render — proves tests are load-bearing."""

    def test_noop_check_version_allows_render(self) -> None:
        """Patching _check_version to no-op lets render succeed (mutant proves gate tested)."""
        with patch("gitweave.module_render._check_version"):
            with tempfile.TemporaryDirectory() as tmp:
                render_module(
                    "python_service",
                    tmp,
                    data={"service_name": "smoke", "repo_name": "smoke"},
                )
                rendered = list(Path(tmp).rglob("*"))
                assert rendered, (
                    "Expected files rendered when enforcement bypassed; "
                    "if empty, the fixture module is broken independently of version check"
                )

    def test_real_check_version_would_block_this_render(self) -> None:
        """Without the no-op, the same render call raises — confirming the mutant test's value."""
        with patch(
            "gitweave.module_render._installed_copier_version",
            return_value="0.0.1",
        ):
            with tempfile.TemporaryDirectory() as tmp:
                with pytest.raises(CopierVersionError):
                    render_module("python_service", tmp)
