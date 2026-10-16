"""B7: Real gw CLI subprocess exits non-zero when config/policy.yaml is absent.

Runs [sys.executable, '-m', 'gitweave.cli', 'self-serve', ...] as a subprocess
in a temporary directory that has no config/policy.yaml.  The real CLI must exit
non-zero and name 'config/policy.yaml' in stderr.

This replaces the synthetic 'python -c' stand-in that was in
tests/test_policy.py::test_absent_policy_exits_nonzero.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


class TestCliPolicyAbsentReal:
    """Real gw CLI subprocess test for missing config/policy.yaml."""

    # Project root is two levels up from tests/
    _PROJECT_ROOT = Path(__file__).parent.parent

    def _run_gw_in_empty_dir(self, tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
        """Run gw CLI in *tmp_path* which has no config/policy.yaml."""
        import site as _site
        env = {**os.environ}
        # Ensure gitweave package is importable from the project root.
        # Also preserve user site-packages so PyGithub etc. remain importable.
        user_site = _site.getusersitepackages()
        existing_pp = env.get("PYTHONPATH", "")
        paths = [str(self._PROJECT_ROOT), user_site]
        if existing_pp:
            paths.append(existing_pp)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        # Strip any existing GW_CALLER_TOKEN — we want the PolicyError to trigger,
        # not a CallerTokenRequiredError.  Auth is bypassed by a fake token.
        env["GW_CALLER_TOKEN"] = "fake-token-for-policy-absent-test"
        env.setdefault("GW_ORG", "fake-org")

        return subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "self-serve", *extra_args],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )

    def test_absent_policy_exits_nonzero_new_repo(self, tmp_path: Path):
        """gw self-serve new-repo exits non-zero when config/policy.yaml is absent."""
        result = self._run_gw_in_empty_dir(
            tmp_path,
            "new-repo", "--team", "platform", "--name", "test-repo",
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when policy.yaml absent.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_absent_policy_stderr_names_config_path(self, tmp_path: Path):
        """stderr names 'config/policy.yaml' when the file is absent."""
        result = self._run_gw_in_empty_dir(
            tmp_path,
            "new-repo", "--team", "platform", "--name", "test-repo",
        )
        combined = result.stdout + result.stderr
        assert "config/policy.yaml" in combined, (
            f"Expected 'config/policy.yaml' in output when policy absent.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_absent_policy_exits_nonzero_update_content(self, tmp_path: Path):
        """gw self-serve update-content exits non-zero when config/policy.yaml is absent."""
        result = self._run_gw_in_empty_dir(
            tmp_path,
            "update-content", "--team", "platform", "--repo", "my-repo",
            "--setting", "description", "--value", "v",
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when policy.yaml absent.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        combined = result.stdout + result.stderr
        assert "config/policy.yaml" in combined

    def test_absent_policy_exits_nonzero_add_exception(self, tmp_path: Path):
        """gw self-serve add-exception exits non-zero when config/policy.yaml is absent."""
        result = self._run_gw_in_empty_dir(
            tmp_path,
            "add-exception", "--team", "platform", "--repo", "my-repo",
            "--exception", "skip-codeowners", "--reason", "test",
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when policy.yaml absent.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        combined = result.stdout + result.stderr
        assert "config/policy.yaml" in combined

    def test_absent_policy_exits_nonzero_list_exceptions(self, tmp_path: Path):
        """gw self-serve list-exceptions exits non-zero when config/policy.yaml is absent."""
        result = self._run_gw_in_empty_dir(
            tmp_path,
            "list-exceptions", "--team", "platform", "--repo", "my-repo",
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when policy.yaml absent.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        combined = result.stdout + result.stderr
        assert "config/policy.yaml" in combined
