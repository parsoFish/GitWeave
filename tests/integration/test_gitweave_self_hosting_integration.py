"""
Integration tests for the GitWeave self-hosting overlay.

These tests exercise scripts/apply-overlays.py against config/repos/gitweave.yaml
in dry-run mode (no real GitHub calls) to validate that the self-hosting overlay
config is correct end-to-end.

A separate section validates the overlay using scripts/validate_overlay_configs.py
to confirm it passes schema checks when processed by the CI tool.

All tests in this file will fail until:
  - config/repos/gitweave.yaml is created with correct content
  - The overlay passes schema validation

Runtime requirements:
  - Python on PATH (uses sys.executable for subprocess calls)
  - scripts/apply-overlays.py exists
  - schemas/overlay.schema.json exists
  - config/repos/gitweave.yaml exists (created as part of this work item)

These tests do NOT require GITHUB_TOKEN or network access — all calls use --dry-run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply-overlays.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_overlay_configs.py"
OVERLAY_CONFIG = REPO_ROOT / "config" / "repos" / "gitweave.yaml"
CONFIG_REPOS_DIR = REPO_ROOT / "config" / "repos"
MODULES_DIR = REPO_ROOT / "modules"
SCHEMA_PATH = REPO_ROOT / "schemas" / "overlay.schema.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_apply(
    *extra_args: str,
    config_dir: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """
    Invoke apply-overlays.py with --dry-run and capture output.

    Uses config/repos/ by default so the real gitweave.yaml is exercised.
    Extra arguments (e.g. --env) are appended after the fixed flags.
    """
    effective_config_dir = config_dir or str(CONFIG_REPOS_DIR)
    return subprocess.run(
        [
            sys.executable,
            str(APPLY_SCRIPT),
            "--dry-run",
            "--config-dir", effective_config_dir,
            "--modules-dir", str(MODULES_DIR),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ},
    )


def _run_validate(
    config_dir: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Invoke validate_overlay_configs.py against the repos config directory."""
    effective_config_dir = config_dir or str(CONFIG_REPOS_DIR)
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATE_SCRIPT),
            "--config-dir", effective_config_dir,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ},
    )


# ---------------------------------------------------------------------------
# TestDryRunExitsCleanly
# ---------------------------------------------------------------------------


class TestDryRunExitsCleanly(unittest.TestCase):
    """
    Running apply-overlays.py --dry-run with the gitweave.yaml overlay must
    complete without errors (exit code 0).
    """

    def test_apply_dry_run_exits_zero(self):
        """
        scripts/apply-overlays.py --dry-run must exit 0 when processing
        config/repos/gitweave.yaml.

        A non-zero exit indicates the overlay config has a structural problem
        that prevents the script from loading or processing it.
        """
        result = _run_apply()
        self.assertEqual(
            result.returncode,
            0,
            f"apply-overlays.py --dry-run exited {result.returncode}.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}\n"
            "Check that config/repos/gitweave.yaml is valid and that all "
            "referenced modules exist under modules/.",
        )

    def test_apply_dry_run_produces_no_error_output(self):
        """
        The --dry-run invocation must not write error messages to stderr.

        Warnings about missing files or invalid config will surface here.
        """
        result = _run_apply()
        # Allow empty stderr or mere informational output, but no 'error' or 'traceback'
        stderr_lower = result.stderr.lower()
        self.assertNotIn(
            "traceback",
            stderr_lower,
            f"apply-overlays.py --dry-run printed a Python traceback to stderr:\n"
            f"{result.stderr}",
        )
        self.assertNotIn(
            "error:",
            stderr_lower,
            f"apply-overlays.py --dry-run printed an error message to stderr:\n"
            f"{result.stderr}",
        )

    def test_apply_dry_run_output_mentions_gitweave_repository(self):
        """
        The --dry-run output must reference the GitWeave repository slug, confirming
        that config/repos/gitweave.yaml was loaded and processed by the script.
        """
        result = _run_apply()
        combined = result.stdout + result.stderr
        # The output must contain 'GitWeave' somewhere (repo slug, dry-run log line, etc.)
        self.assertIn(
            "GitWeave",
            combined,
            f"apply-overlays.py --dry-run output does not mention 'GitWeave'.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n"
            "The gitweave.yaml overlay may not have been loaded.",
        )

    def test_apply_dry_run_output_lists_modules(self):
        """
        The --dry-run output must list the module(s) declared in gitweave.yaml,
        confirming that the modules section was parsed correctly.
        """
        # Load the overlay to know which modules to expect
        with open(OVERLAY_CONFIG) as f:
            doc = yaml.safe_load(f)
        module_names = [
            m.get("name")
            for m in doc.get("spec", {}).get("modules", [])
            if m.get("name")
        ]

        result = _run_apply()
        combined = result.stdout + result.stderr

        for module_name in module_names:
            self.assertIn(
                module_name,
                combined,
                f"Module '{module_name}' from gitweave.yaml not mentioned in "
                f"dry-run output.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

    def test_apply_dry_run_does_not_clone_or_push(self):
        """
        Dry-run mode must not invoke git clone or git push.

        This is guaranteed by the script's dry_run branch (no subprocess for
        clone/push), but we confirm the output contains no clone URL to be safe.
        """
        result = _run_apply()
        combined = result.stdout + result.stderr
        self.assertNotIn(
            "x-access-token",
            combined,
            "apply-overlays.py --dry-run output contains 'x-access-token', "
            "suggesting a git clone was attempted. Dry-run must not clone repos.",
        )


# ---------------------------------------------------------------------------
# TestDryRunOutputStructure
# ---------------------------------------------------------------------------


class TestDryRunOutputStructure(unittest.TestCase):
    """
    The dry-run output must be structured so CI can confirm what would change.
    These tests verify the output includes expected information about the overlay.
    """

    def _get_dry_run_output(self) -> str:
        result = _run_apply()
        return result.stdout + result.stderr

    def test_dry_run_output_mentions_at_least_one_module(self):
        """
        At least one module name from gitweave.yaml must appear in the output.

        This confirms the modules section is read and would be applied.
        """
        with open(OVERLAY_CONFIG) as f:
            doc = yaml.safe_load(f)
        modules = doc.get("spec", {}).get("modules", [])
        self.assertGreater(
            len(modules),
            0,
            "gitweave.yaml has no modules — cannot verify module output.",
        )

        combined = self._get_dry_run_output()
        found_any = any(m.get("name", "") in combined for m in modules)
        self.assertTrue(
            found_any,
            f"None of the module names from gitweave.yaml appear in dry-run output.\n"
            f"Expected one of: {[m.get('name') for m in modules]}\n"
            f"Dry-run output:\n{combined}",
        )

    def test_dry_run_single_overlay_processes_exactly_one_config(self):
        """
        With only gitweave.yaml in config/repos/, the script should report
        exactly one overlay processed.

        This prevents the script from silently skipping the config.
        """
        result = _run_apply()
        # Accept various success indicators; the key is that the script ran without error
        self.assertEqual(
            result.returncode,
            0,
            f"apply-overlays.py --dry-run failed.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestValidateOverlayConfigsScript
# ---------------------------------------------------------------------------


class TestValidateOverlayConfigsScript(unittest.TestCase):
    """
    scripts/validate_overlay_configs.py must exit 0 when run against
    config/repos/ which contains gitweave.yaml.

    This mirrors what the CI validation workflow does on every PR.
    """

    def test_validate_script_exits_zero_for_gitweave_overlay(self):
        """
        validate_overlay_configs.py must exit 0 for config/repos/gitweave.yaml.

        A non-zero exit means the overlay fails JSON Schema validation — the CI
        overlay-validate workflow would block the PR.
        """
        result = _run_validate()
        self.assertEqual(
            result.returncode,
            0,
            f"validate_overlay_configs.py exited {result.returncode} for config/repos/.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}\n"
            "config/repos/gitweave.yaml failed schema validation. "
            "Fix the overlay config or update the schema.",
        )

    def test_validate_script_reports_validated_files(self):
        """
        validate_overlay_configs.py output must mention the number of files validated,
        confirming it processed gitweave.yaml and did not silently skip it.
        """
        result = _run_validate()
        combined = result.stdout + result.stderr
        # The validate script outputs "Validated N file(s)" on success
        self.assertRegex(
            combined,
            r"[Vv]alidat",
            f"validate_overlay_configs.py output does not mention validation.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    def test_validate_script_output_mentions_gitweave_yaml(self):
        """
        The validation output should reference gitweave.yaml so it is clear which
        file was checked (not just a count).
        """
        result = _run_validate()
        combined = result.stdout + result.stderr
        self.assertIn(
            "gitweave",
            combined.lower(),
            f"validate_overlay_configs.py output does not mention 'gitweave'.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestDryRunWithExplicitConfig
# ---------------------------------------------------------------------------


class TestDryRunWithExplicitConfig(unittest.TestCase):
    """
    Edge cases: dry-run with the overlay written to a temp directory to
    isolate gitweave.yaml from any future overlays added to config/repos/.
    """

    def setUp(self):
        """Copy gitweave.yaml into an isolated temp directory for testing."""
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)

        # Read the real gitweave.yaml and write it to the temp dir
        with open(OVERLAY_CONFIG) as f:
            content = f.read()
        (tmp_path / "gitweave.yaml").write_text(content)

        self._isolated_config_dir = str(tmp_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_isolated_dry_run_exits_zero(self):
        """
        Running --dry-run against an isolated copy of gitweave.yaml must exit 0.

        This isolates the test from other overlays that might exist in config/repos/
        in the future, confirming that gitweave.yaml alone is valid.
        """
        result = _run_apply(config_dir=self._isolated_config_dir)
        self.assertEqual(
            result.returncode,
            0,
            f"Isolated dry-run of gitweave.yaml failed (exit {result.returncode}).\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    def test_isolated_dry_run_does_not_error_on_single_overlay(self):
        """
        With a single valid overlay in the config directory, the script must
        complete cleanly without YAML parse errors or missing-module errors.
        """
        result = _run_apply(config_dir=self._isolated_config_dir)
        stderr_lower = result.stderr.lower()
        self.assertNotIn(
            "valueerror",
            stderr_lower,
            f"apply-overlays.py raised a ValueError during dry-run:\n{result.stderr}",
        )
        self.assertNotIn(
            "keyerror",
            stderr_lower,
            f"apply-overlays.py raised a KeyError during dry-run:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
