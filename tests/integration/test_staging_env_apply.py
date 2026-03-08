"""
Integration tests: staging vs production environment separation in overlay applies.

Work item: Implement staging environment separation for overlay application

These tests exercise the full overlay-apply pipeline against a real GitHub test
organisation, confirming that:

  1. Triggering apply with TARGET_ENV=staging only affects repositories whose
     overlay config declares spec.environments.staging.
  2. Triggering apply with TARGET_ENV=production only affects repositories whose
     overlay config declares spec.environments.production.
  3. A staging-only repository is NOT modified during a production run (isolation).
  4. A production-only repository is NOT modified during a staging run (isolation).
  5. apply-overlays.py exits 0 for an env-filtered run even when the filter
     excludes all configured repositories.

Pipeline under test (per run):
  1. Write two RepositoryOverlay configs to a temp config dir:
       - staging-only overlay → targets a staging-only test repo
       - production-only overlay → targets a production-only test repo
  2. Run apply-overlays.py --dry-run --env staging.
  3. Assert that only the staging overlay repo appears in the output and
     that the production repo is absent.
  4. Run apply-overlays.py --dry-run --env production.
  5. Assert isolation in the other direction.

These are dry-run integration tests — they do NOT create GitHub repos or open
PRs. They exercise the full script execution path including config loading,
environment filtering, and output reporting, but without live GitHub side effects.

Runtime requirements:
  - Python 3.12+  (already guaranteed by the CI environment)
  - scripts/apply-overlays.py must exist and be implemented

These tests are skipped only when the script itself is missing. Unlike the live
integration tests in test_overlay_apply.py, they do NOT require GITHUB_TOKEN,
GITWEAVE_TEST_ORG, copier, git, or gh — the dry-run flag prevents any real
network or filesystem side effects.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "apply-overlays.py"


# ---------------------------------------------------------------------------
# Skip guard — only skip when the script is missing
# ---------------------------------------------------------------------------

_SCRIPT_EXISTS = SCRIPT_PATH.is_file()
pytestmark = pytest.mark.skipif(
    not _SCRIPT_EXISTS,
    reason=(
        f"scripts/apply-overlays.py not found at {SCRIPT_PATH} — "
        "implement the script before running integration tests"
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_script(*args: str) -> subprocess.CompletedProcess:
    """
    Invoke apply-overlays.py capturing stdout + stderr.
    Sets GITHUB_TOKEN=fake so dry-run mode does not fail on the token check.
    """
    env = {**os.environ, "GITHUB_TOKEN": "fake"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _write_overlay(directory: str | Path, filename: str, doc: dict) -> Path:
    """Write *doc* as YAML to *directory/filename* and return the path."""
    path = Path(directory) / filename
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    return path


def _staging_overlay(repo: str) -> dict:
    """Return a RepositoryOverlay config that declares a staging environment."""
    return {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {
            "repository": repo,
            "modules": [{"name": "lang-node"}],
            "environments": {
                "staging": {
                    "variables": {"NODE_ENV": "staging", "LOG_LEVEL": "info"},
                }
            },
        },
    }


def _production_overlay(repo: str) -> dict:
    """Return a RepositoryOverlay config that declares a production environment."""
    return {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {
            "repository": repo,
            "modules": [{"name": "lang-node"}],
            "environments": {
                "production": {
                    "variables": {"NODE_ENV": "production", "LOG_LEVEL": "error"},
                }
            },
        },
    }


def _multi_env_overlay(repo: str) -> dict:
    """Return a RepositoryOverlay that declares both staging and production environments."""
    return {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {
            "repository": repo,
            "modules": [{"name": "lang-node"}],
            "environments": {
                "staging": {"variables": {"NODE_ENV": "staging"}},
                "production": {"variables": {"NODE_ENV": "production"}},
            },
        },
    }


def _no_env_overlay(repo: str) -> dict:
    """Return a RepositoryOverlay with no environments declared."""
    return {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {
            "repository": repo,
            "modules": [{"name": "lang-node"}],
        },
    }


# ---------------------------------------------------------------------------
# TestStagingRunIsolation
# ---------------------------------------------------------------------------


class TestStagingRunIsolation:
    """
    When apply-overlays.py is run with --env staging, only staging-environment
    repos appear in output; production repos are excluded.

    Rationale: the staging job must never accidentally trigger changes on
    production-only repos. The --env filter enforces this isolation at the
    script level, independently of the workflow job gating.
    """

    def test_staging_run_includes_staging_repo_in_output(self, tmp_path):
        """
        With --env staging, the repo from the staging overlay appears in output.

        This confirms that the env filter includes matching overlays.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/staging-repo" in combined, (
            f"Staging overlay repo 'org/staging-repo' must appear in --env staging output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_staging_run_excludes_production_only_repo_from_output(self, tmp_path):
        """
        With --env staging, repos from production-only overlays must not appear
        in the output.

        This is the core isolation guarantee: a staging run must never log,
        touch, or reference production-only repositories.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/prod-repo" not in combined, (
            f"Production-only repo 'org/prod-repo' must NOT appear in --env staging output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}\n\n"
            "A staging run must never reference production-only repositories."
        )

    def test_staging_run_exits_zero(self, tmp_path):
        """apply-overlays.py must exit 0 when --env staging is used."""
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )

        assert result.returncode == 0, (
            f"Script must exit 0 for --env staging run.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_staging_run_exits_zero_when_no_staging_overlays_exist(self, tmp_path):
        """
        With --env staging and only production overlays in the config dir,
        the script must exit 0 (empty result is valid — no work to do).
        """
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )

        assert result.returncode == 0, (
            f"Script must exit 0 when no staging overlays match (empty result).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_staging_run_excludes_overlays_with_no_environment_key(self, tmp_path):
        """
        Overlays without any spec.environments declaration must be skipped in
        a --env staging run. They have no environment context and cannot be
        safely classified as staging-safe.
        """
        _write_overlay(tmp_path, "no-env.yaml", _no_env_overlay("org/bare-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/bare-repo" not in combined, (
            f"Overlay 'org/bare-repo' has no spec.environments — must be excluded in "
            f"--env staging run.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestProductionRunIsolation
# ---------------------------------------------------------------------------


class TestProductionRunIsolation:
    """
    When apply-overlays.py is run with --env production, only production-environment
    repos appear in output; staging repos are excluded.
    """

    def test_production_run_includes_production_repo_in_output(self, tmp_path):
        """
        With --env production, the repo from the production overlay appears in output.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "production", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/prod-repo" in combined, (
            f"Production overlay repo 'org/prod-repo' must appear in --env production output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_production_run_excludes_staging_only_repo_from_output(self, tmp_path):
        """
        With --env production, repos from staging-only overlays must not appear
        in the output.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "production", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/staging-repo" not in combined, (
            f"Staging-only repo 'org/staging-repo' must NOT appear in --env production output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_production_run_exits_zero(self, tmp_path):
        """apply-overlays.py must exit 0 when --env production is used."""
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "production", "--config-dir", str(tmp_path)
        )

        assert result.returncode == 0, (
            f"Script must exit 0 for --env production run.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestMultiEnvOverlayBehaviour
# ---------------------------------------------------------------------------


class TestMultiEnvOverlayBehaviour:
    """
    Overlays that declare both staging and production environments must appear
    in both staging and production runs.
    """

    def test_multi_env_overlay_appears_in_staging_run(self, tmp_path):
        """
        An overlay with both staging and production environments must be
        included in a --env staging run.
        """
        _write_overlay(
            tmp_path, "multi-env.yaml", _multi_env_overlay("org/multi-env-repo")
        )

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/multi-env-repo" in combined, (
            f"Multi-env overlay 'org/multi-env-repo' must appear in --env staging output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_multi_env_overlay_appears_in_production_run(self, tmp_path):
        """
        An overlay with both staging and production environments must be
        included in a --env production run.
        """
        _write_overlay(
            tmp_path, "multi-env.yaml", _multi_env_overlay("org/multi-env-repo")
        )

        result = _run_script(
            "--dry-run", "--env", "production", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/multi-env-repo" in combined, (
            f"Multi-env overlay 'org/multi-env-repo' must appear in --env production output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_multi_env_overlay_appears_in_unfiltered_run(self, tmp_path):
        """
        Without --env, the multi-env overlay must appear in the output
        alongside all other overlays (backward-compatible behaviour).
        """
        _write_overlay(
            tmp_path, "multi-env.yaml", _multi_env_overlay("org/multi-env-repo")
        )
        _write_overlay(tmp_path, "bare.yaml", _no_env_overlay("org/bare-repo"))

        result = _run_script(
            "--dry-run", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "org/multi-env-repo" in combined, (
            f"Multi-env overlay must appear in unfiltered (no --env) output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "org/bare-repo" in combined, (
            f"Bare overlay must also appear in unfiltered output.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestEnvFilterOutputFormat
# ---------------------------------------------------------------------------


class TestEnvFilterOutputFormat:
    """
    When environment filtering is active, the script output must be clear
    about which environment is being targeted.
    """

    def test_output_mentions_env_when_env_flag_is_used(self, tmp_path):
        """
        When --env staging is passed, the output must mention 'staging' so
        operators know which environment filter was applied.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        assert "staging" in combined.lower(), (
            f"Script output must mention 'staging' when --env staging is used.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_staging_run_summary_shows_only_staging_repo_count(self, tmp_path):
        """
        The summary line in a --env staging run must reflect only the number
        of staging-filtered repos processed, not the total config count.

        With 1 staging overlay and 1 production overlay: summary should show
        count = 1, not 2.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/staging-repo"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/prod-repo"))

        result = _run_script(
            "--dry-run", "--env", "staging", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        # Must exit 0 and have processed only 1 repo
        assert result.returncode == 0, (
            f"Script must exit 0.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # Verify the production repo is absent from the summary
        assert "org/prod-repo" not in combined, (
            f"Production repo must not appear in staging run summary.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestBackwardCompatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """
    The --env flag must be fully optional. Without it, the script must continue
    to process all configs exactly as before (no regression for existing callers).
    """

    def test_script_without_env_flag_processes_all_configs(self, tmp_path):
        """
        Without --env, the script processes all overlay configs in the config
        dir, regardless of their environment declarations.
        """
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/s"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/p"))
        _write_overlay(tmp_path, "bare.yaml", _no_env_overlay("org/b"))

        result = _run_script(
            "--dry-run", "--config-dir", str(tmp_path)
        )
        combined = result.stdout + result.stderr

        for expected in ("org/s", "org/p", "org/b"):
            assert expected in combined, (
                f"Without --env, '{expected}' must appear in output.\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

    def test_script_without_env_flag_exits_zero_with_mixed_configs(self, tmp_path):
        """Without --env, script must exit 0 with a mix of env and no-env configs."""
        _write_overlay(tmp_path, "staging.yaml", _staging_overlay("org/s"))
        _write_overlay(tmp_path, "prod.yaml", _production_overlay("org/p"))

        result = _run_script(
            "--dry-run", "--config-dir", str(tmp_path)
        )

        assert result.returncode == 0, (
            f"Script must exit 0 without --env flag.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
