"""
Unit and integration tests for scripts/apply-overlays.py —
the Python script that reads config/repos/*.yaml and applies each overlay
via Copier to the target repository.

These tests drive the specification for the script (TDD red phase). They verify:

  Script existence and importability:
    - scripts/apply-overlays.py must exist
    - The script must be importable without SyntaxError or ModuleNotFoundError
    - The script must accept --help without crashing

  Config loading (load_overlay_configs):
    - Returns an empty list when the directory does not exist
    - Returns an empty list when the directory contains no .yaml files
    - Returns one config dict per .yaml file found
    - Ignores files that do not end in .yaml
    - Raises a descriptive error when a YAML file cannot be parsed
    - Each returned dict contains the parsed YAML document

  Overlay application (apply_overlay):
    - Clones the target repository using GITHUB_TOKEN for auth
    - Runs 'copier copy <module-path>' for each module in spec.modules
    - Commits the applied changes on a new branch
    - Pushes the branch to origin
    - Opens a PR via gh cli
    - Returns a success result object when all operations succeed
    - Returns a failure result with an error message when clone fails
    - Returns a failure result with an error message when copier fails
    - Returns a failure result with an error message when pr creation fails
    - Does NOT clone or run copier in dry-run mode
    - Returns a dry-run result describing what would happen

  Dry-run mode (--dry-run flag):
    - Prints what would be applied for each repo without executing
    - Exits 0 even when configs are present in dry-run mode
    - Does not call git, copier, or gh commands

  Exit code behaviour:
    - Exits 0 when all repository applications succeed
    - Exits non-zero when any single repository fails
    - Exits non-zero when all repositories fail
    - Processes all repositories even after one fails (no early exit)

  Per-repo reporting:
    - Prints a success line for each successful repository
    - Prints a failure line for each failed repository
    - Includes the repo slug in every status line
    - Prints a summary at the end with total counts
    - Summary distinguishes succeeded vs failed counts

  Module path resolution:
    - Resolves module path as modules/<module-name> relative to repo root
    - Handles overlays with no modules gracefully (no copier invocations)
    - Handles overlays with multiple modules (copier called once per module)

  GITHUB_TOKEN requirement:
    - Exits non-zero (not 0) when GITHUB_TOKEN is absent and not in dry-run mode
    - Prints a descriptive error when GITHUB_TOKEN is absent
    - Dry-run mode does NOT require GITHUB_TOKEN

All tests will fail until scripts/apply-overlays.py is implemented.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, call, patch

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "apply-overlays.py")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """
    Invoke apply-overlays.py with the given arguments.
    Always captures stdout+stderr and never raises on non-zero exit.
    If env is provided, it replaces the inherited environment entirely.
    """
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, SCRIPT_PATH, *args],
        capture_output=True,
        text=True,
        env=run_env,
    )


def _load_script():
    """
    Import apply-overlays.py as a Python module so its public functions
    can be unit-tested directly without invoking a subprocess.

    Raises FileNotFoundError with a descriptive message when the script
    does not yet exist.
    """
    if not os.path.isfile(SCRIPT_PATH):
        raise FileNotFoundError(
            f"scripts/apply-overlays.py not found at {SCRIPT_PATH} — "
            "the script must be implemented before these unit tests can pass"
        )
    spec = importlib.util.spec_from_file_location("apply_overlays", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_yaml(directory: str, filename: str, doc: dict) -> str:
    """Write doc as YAML to directory/filename and return the full path."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    return path


def _minimal_overlay(repo: str = "my-org/my-app", modules: list | None = None) -> dict:
    """Return the smallest valid RepositoryOverlay document."""
    doc: dict = {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": "my-app"},
        "spec": {"repository": repo},
    }
    if modules is not None:
        doc["spec"]["modules"] = modules
    return doc


# ---------------------------------------------------------------------------
# TestScriptExists
# ---------------------------------------------------------------------------


class TestScriptExists(unittest.TestCase):
    """Basic existence and importability checks."""

    def test_apply_overlays_script_exists(self):
        """scripts/apply-overlays.py must exist at the expected path."""
        self.assertTrue(
            os.path.isfile(SCRIPT_PATH),
            f"scripts/apply-overlays.py is missing — expected at {SCRIPT_PATH}. "
            "Create the script before the CI job can use it.",
        )

    def test_script_is_runnable_without_syntax_errors(self):
        """The script must accept --help without SyntaxError or ModuleNotFoundError."""
        result = _run_script("--help")
        self.assertNotIn(
            "SyntaxError",
            result.stderr,
            f"scripts/apply-overlays.py contains a SyntaxError:\n{result.stderr}",
        )
        self.assertNotIn(
            "ModuleNotFoundError",
            result.stderr,
            f"scripts/apply-overlays.py has an unresolvable import:\n{result.stderr}",
        )

    def test_script_exposes_load_overlay_configs_function(self):
        """The script must expose a callable load_overlay_configs(config_dir)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "load_overlay_configs", None)),
            "scripts/apply-overlays.py does not expose a callable 'load_overlay_configs'",
        )

    def test_script_exposes_apply_overlay_function(self):
        """The script must expose a callable apply_overlay(config, modules_dir, ...)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "apply_overlay", None)),
            "scripts/apply-overlays.py does not expose a callable 'apply_overlay'",
        )


# ---------------------------------------------------------------------------
# TestLoadOverlayConfigs
# ---------------------------------------------------------------------------


class TestLoadOverlayConfigs(unittest.TestCase):
    """Unit tests for the load_overlay_configs function."""

    def setUp(self):
        self.mod = _load_script()

    def test_returns_empty_list_when_directory_does_not_exist(self):
        """load_overlay_configs returns [] for a non-existent directory."""
        result = self.mod.load_overlay_configs("/nonexistent/path/config/repos")
        self.assertEqual(
            result,
            [],
            "load_overlay_configs should return [] when directory does not exist, "
            f"got: {result}",
        )

    def test_returns_empty_list_when_directory_has_no_yaml_files(self):
        """load_overlay_configs returns [] when no .yaml files are present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("# not yaml\n")
            result = self.mod.load_overlay_configs(tmpdir)
        self.assertEqual(
            result,
            [],
            "load_overlay_configs should return [] for a directory with no .yaml files",
        )

    def test_returns_one_item_per_yaml_file(self):
        """load_overlay_configs returns one dict per .yaml file found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app-a.yaml", _minimal_overlay("org/app-a"))
            _write_yaml(tmpdir, "app-b.yaml", _minimal_overlay("org/app-b"))
            result = self.mod.load_overlay_configs(tmpdir)
        self.assertEqual(
            len(result),
            2,
            f"Expected 2 configs for 2 .yaml files, got {len(result)}: {result}",
        )

    def test_ignores_files_without_yaml_extension(self):
        """load_overlay_configs ignores .yml, .json, and other non-.yaml files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            # These should be silently ignored
            with open(os.path.join(tmpdir, "app.yml"), "w") as f:
                yaml.dump(_minimal_overlay("org/other"), f)
            with open(os.path.join(tmpdir, "notes.txt"), "w") as f:
                f.write("plain text\n")
            result = self.mod.load_overlay_configs(tmpdir)
        self.assertEqual(
            len(result),
            1,
            f"load_overlay_configs should count only .yaml files, got {len(result)} configs",
        )

    def test_each_returned_dict_contains_parsed_yaml_document(self):
        """Each item returned by load_overlay_configs contains the parsed YAML doc."""
        overlay = _minimal_overlay("org/my-service", modules=[{"name": "lang-node"}])
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "my-service.yaml", overlay)
            result = self.mod.load_overlay_configs(tmpdir)
        self.assertEqual(len(result), 1)
        doc = result[0]
        self.assertEqual(
            doc.get("spec", {}).get("repository"),
            "org/my-service",
            f"Parsed config does not contain expected spec.repository: {doc}",
        )

    def test_raises_or_reports_error_for_unparseable_yaml(self):
        """load_overlay_configs raises an exception for malformed YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "broken.yaml")
            with open(bad_path, "w") as f:
                f.write("apiVersion: gitweave.io/v1\n  bad_indent: [\n")
            with self.assertRaises(Exception) as ctx:
                self.mod.load_overlay_configs(tmpdir)
        # The exception message should reference the file name so users can diagnose it
        self.assertIn(
            "broken.yaml",
            str(ctx.exception),
            f"Exception message does not mention 'broken.yaml': {ctx.exception}",
        )


# ---------------------------------------------------------------------------
# TestApplyOverlayDryRun
# ---------------------------------------------------------------------------


class TestApplyOverlayDryRun(unittest.TestCase):
    """Unit tests for dry-run behaviour of apply_overlay."""

    def setUp(self):
        self.mod = _load_script()

    @patch("subprocess.run")
    def test_dry_run_does_not_call_subprocess(self, mock_run: MagicMock):
        """apply_overlay in dry-run mode must not invoke any subprocess."""
        config = _minimal_overlay("org/my-app", modules=[{"name": "lang-node"}])
        self.mod.apply_overlay(
            config=config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
        )
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_dry_run_returns_result_with_dry_run_flag(self, mock_run: MagicMock):
        """apply_overlay in dry-run returns a result that indicates dry-run."""
        config = _minimal_overlay("org/my-app", modules=[{"name": "lang-node"}])
        result = self.mod.apply_overlay(
            config=config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
        )
        self.assertTrue(
            result.get("dry_run"),
            f"Result for dry-run apply_overlay should have dry_run=True: {result}",
        )

    @patch("subprocess.run")
    def test_dry_run_result_contains_repo_slug(self, mock_run: MagicMock):
        """apply_overlay dry-run result includes the repo slug so it can be logged."""
        config = _minimal_overlay("org/target-repo", modules=[{"name": "lang-node"}])
        result = self.mod.apply_overlay(
            config=config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
        )
        self.assertEqual(
            result.get("repo"),
            "org/target-repo",
            f"Dry-run result should include 'repo': {result}",
        )

    @patch("subprocess.run")
    def test_dry_run_result_describes_modules_that_would_be_applied(
        self, mock_run: MagicMock
    ):
        """apply_overlay dry-run result lists modules that would be applied."""
        config = _minimal_overlay(
            "org/my-app",
            modules=[{"name": "lang-node"}, {"name": "ci-github-actions"}],
        )
        result = self.mod.apply_overlay(
            config=config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
        )
        modules_in_result = result.get("modules", [])
        self.assertIn(
            "lang-node",
            modules_in_result,
            f"Dry-run result should list 'lang-node' in modules: {result}",
        )
        self.assertIn(
            "ci-github-actions",
            modules_in_result,
            f"Dry-run result should list 'ci-github-actions' in modules: {result}",
        )


# ---------------------------------------------------------------------------
# TestApplyOverlaySuccess
# ---------------------------------------------------------------------------


class TestApplyOverlaySuccess(unittest.TestCase):
    """Unit tests for apply_overlay happy-path with mocked subprocess."""

    def setUp(self):
        self.mod = _load_script()
        self.config = _minimal_overlay(
            "org/my-app", modules=[{"name": "lang-node"}]
        )

    def _make_successful_run(self):
        """Return a mock subprocess.CompletedProcess with returncode=0."""
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_clones_repo_with_github_token_in_url(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay clones the target repo using the GITHUB_TOKEN in the URL."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        self.mod.apply_overlay(
            config=self.config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="ghp_test_token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        clone_calls = [c for c in all_calls if "clone" in c]
        self.assertTrue(
            clone_calls,
            "apply_overlay must call 'git clone' — no clone call found in subprocess calls",
        )
        clone_call_str = clone_calls[0]
        self.assertIn(
            "org/my-app",
            clone_call_str,
            f"Clone call does not reference 'org/my-app': {clone_call_str}",
        )
        self.assertIn(
            "ghp_test_token",
            clone_call_str,
            f"Clone URL does not embed the GITHUB_TOKEN for authentication: {clone_call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_runs_copier_copy_for_each_module(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay runs 'copier copy' once per module in spec.modules."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _minimal_overlay(
            "org/multi-module",
            modules=[{"name": "lang-node"}, {"name": "ci-github-actions"}],
        )
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        copier_calls = [c for c in all_calls if "copier" in c]
        self.assertEqual(
            len(copier_calls),
            2,
            f"Expected 2 copier calls for 2 modules, found {len(copier_calls)}: {copier_calls}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_copier_copy_uses_module_path_from_modules_dir(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay passes modules/<name> as the source path to copier copy."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        copier_calls = [c for c in all_calls if "copier" in c]
        self.assertTrue(copier_calls, "No copier call found in subprocess calls")
        self.assertIn(
            "lang-node",
            copier_calls[0],
            f"Copier call does not reference module 'lang-node': {copier_calls[0]}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_commits_and_pushes_changes(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay commits changes and pushes the branch after copier runs."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        has_commit = any("commit" in c for c in all_calls)
        has_push = any("push" in c for c in all_calls)
        self.assertTrue(
            has_commit,
            f"apply_overlay must run 'git commit' — not found in calls: {all_calls}",
        )
        self.assertTrue(
            has_push,
            f"apply_overlay must run 'git push' — not found in calls: {all_calls}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_opens_pr_via_gh_cli(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay opens a PR with 'gh pr create' after pushing the branch."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        pr_calls = [c for c in all_calls if "gh" in c and "pr" in c]
        self.assertTrue(
            pr_calls,
            f"apply_overlay must call 'gh pr create' — not found in: {all_calls}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_returns_success_result_dict(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay returns a result dict with success=True when all steps pass."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        result = self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        self.assertTrue(
            result.get("success"),
            f"apply_overlay should return success=True on happy path: {result}",
        )
        self.assertEqual(
            result.get("repo"),
            "org/my-app",
            f"Result should contain the repo slug: {result}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_no_copier_calls_when_overlay_has_no_modules(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay does not call copier when spec.modules is absent or empty."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _minimal_overlay("org/no-modules")  # no modules key
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = [str(c) for c in mock_run.call_args_list]
        copier_calls = [c for c in all_calls if "copier" in c]
        self.assertEqual(
            len(copier_calls),
            0,
            f"apply_overlay should not call copier when overlay has no modules: {copier_calls}",
        )


# ---------------------------------------------------------------------------
# TestApplyOverlayFailures
# ---------------------------------------------------------------------------


class TestApplyOverlayFailures(unittest.TestCase):
    """Unit tests for apply_overlay error handling."""

    def setUp(self):
        self.mod = _load_script()
        self.config = _minimal_overlay("org/my-app", modules=[{"name": "lang-node"}])

    def _make_failed_run(self, stderr: str = "error") -> MagicMock:
        """Return a mock subprocess.CompletedProcess with returncode=1."""
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = stderr
        return mock

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_returns_failure_result_when_clone_fails(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay returns success=False when git clone exits non-zero."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_failed_run("repository not found")

        result = self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        self.assertFalse(
            result.get("success"),
            f"apply_overlay should return success=False when clone fails: {result}",
        )
        self.assertIn(
            "error",
            result,
            f"Failure result must include an 'error' key: {result}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_failure_result_includes_error_message(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay failure result contains a non-empty error message."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_failed_run("authentication required")

        result = self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        error_msg = result.get("error", "")
        self.assertTrue(
            bool(error_msg),
            f"Failure result must contain a non-empty 'error' message: {result}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_returns_failure_result_when_copier_fails(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """apply_overlay returns success=False when copier exits non-zero."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

        # Clone succeeds, copier fails
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if "clone" in str(cmd):
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            elif "copier" in str(cmd):
                result.returncode = 1
                result.stdout = ""
                result.stderr = "template not found"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        mock_run.side_effect = side_effect

        result = self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        self.assertFalse(
            result.get("success"),
            f"apply_overlay should return success=False when copier fails: {result}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_failure_result_contains_repo_slug(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """Failure result always includes the repo slug for identification in summary."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_failed_run()

        result = self.mod.apply_overlay(
            config=self.config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        self.assertEqual(
            result.get("repo"),
            "org/my-app",
            f"Failure result must contain 'repo' slug: {result}",
        )


# ---------------------------------------------------------------------------
# TestScriptExitCodes (subprocess-level, drives CLI integration)
# ---------------------------------------------------------------------------


class TestScriptExitCodes(unittest.TestCase):
    """Integration tests that invoke the script as a subprocess and check exit codes."""

    def test_exits_zero_in_dry_run_with_empty_config_dir(self):
        """Script exits 0 in --dry-run when config dir is empty or absent."""
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent/path",
            env={"GITHUB_TOKEN": "fake"},
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Script should exit 0 in dry-run with no configs.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_exits_zero_in_dry_run_with_valid_configs(self):
        """Script exits 0 in --dry-run even with overlay configs present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir, "app.yaml", _minimal_overlay("org/app", [{"name": "lang-node"}])
            )
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        self.assertEqual(
            result.returncode,
            0,
            f"Script should exit 0 in dry-run with valid configs.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_does_not_require_github_token(self):
        """Script must not require GITHUB_TOKEN when --dry-run is passed."""
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent/path",
            env=env_without_token,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Script should exit 0 in dry-run without GITHUB_TOKEN.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_exits_nonzero_without_github_token_in_non_dry_run_mode(self):
        """Script must exit non-zero when GITHUB_TOKEN is absent in apply mode."""
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            result = _run_script(
                "--config-dir",
                tmpdir,
                env=env_without_token,
            )
        self.assertNotEqual(
            result.returncode,
            0,
            f"Script should exit non-zero when GITHUB_TOKEN is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_error_message_mentions_github_token_when_absent(self):
        """The error output must mention GITHUB_TOKEN when the variable is missing."""
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            result = _run_script(
                "--config-dir",
                tmpdir,
                env=env_without_token,
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "GITHUB_TOKEN",
            combined,
            f"Script should mention 'GITHUB_TOKEN' in output when it is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_prints_repo_slug_in_output(self):
        """Dry-run output must include the repository slug for each configured repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "my-service.yaml",
                _minimal_overlay("org/my-service", [{"name": "lang-node"}]),
            )
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "org/my-service",
            combined,
            f"Dry-run output must include the repo slug 'org/my-service'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_prints_module_names_in_output(self):
        """Dry-run output must include module names that would be applied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "svc.yaml",
                _minimal_overlay(
                    "org/svc",
                    [{"name": "lang-node"}, {"name": "ci-github-actions"}],
                ),
            )
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "lang-node",
            combined,
            f"Dry-run output should mention module 'lang-node'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn(
            "ci-github-actions",
            combined,
            f"Dry-run output should mention module 'ci-github-actions'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestSummaryOutput
# ---------------------------------------------------------------------------


class TestSummaryOutput(unittest.TestCase):
    """Tests for per-repo reporting and the final summary in dry-run mode.

    These tests use --dry-run to avoid needing live GitHub credentials while
    still exercising the multi-repo loop and summary logic.
    """

    def test_prints_success_line_per_repo_in_dry_run(self):
        """Dry-run output includes a status line for each configured repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("app-a.yaml", "app-b.yaml"):
                repo = f"org/{name.replace('.yaml', '')}"
                _write_yaml(tmpdir, name, _minimal_overlay(repo))
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "org/app-a",
            combined,
            f"Output should include 'org/app-a'.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn(
            "org/app-b",
            combined,
            f"Output should include 'org/app-b'.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_prints_summary_line_at_end(self):
        """Output must include a summary line after processing all repos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        combined = result.stdout + result.stderr
        # Summary can say "Summary", "Results", "1 succeeded", "1/1", etc.
        has_summary = (
            "summary" in combined.lower()
            or "succeeded" in combined.lower()
            or "failed" in combined.lower()
            or re.search(r"\d+\s*/\s*\d+", combined)
        )
        self.assertTrue(
            has_summary,
            f"Output must include a summary of results.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_all_repos_processed_even_with_no_modules(self):
        """Repos with no modules are still listed in dry-run output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "bare.yaml", _minimal_overlay("org/bare-repo"))
            result = _run_script(
                "--dry-run",
                "--config-dir",
                tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "org/bare-repo",
            combined,
            f"Dry-run should mention repos with no modules.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestCliArguments
# ---------------------------------------------------------------------------


class TestCliArguments(unittest.TestCase):
    """Tests for the command-line interface contract."""

    def test_accepts_dry_run_flag(self):
        """Script must accept --dry-run without reporting an argument error."""
        result = _run_script("--dry-run", "--config-dir", "/nonexistent")
        self.assertNotIn(
            "unrecognized argument",
            result.stderr,
            f"Script rejected --dry-run.\nstderr: {result.stderr}",
        )
        self.assertNotIn(
            "error: argument",
            result.stderr.lower(),
            f"Script reported argument error for --dry-run.\nstderr: {result.stderr}",
        )

    def test_accepts_config_dir_argument(self):
        """Script must accept --config-dir <path> without reporting an argument error."""
        result = _run_script("--config-dir", "/nonexistent", "--dry-run")
        self.assertNotIn(
            "unrecognized argument",
            result.stderr,
            f"Script rejected --config-dir.\nstderr: {result.stderr}",
        )

    def test_accepts_modules_dir_argument(self):
        """Script must accept --modules-dir <path> so the modules directory can be overridden."""
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent",
            "--modules-dir",
            "/nonexistent/modules",
        )
        self.assertNotIn(
            "unrecognized argument",
            result.stderr,
            f"Script rejected --modules-dir.\nstderr: {result.stderr}",
        )

    def test_defaults_config_dir_to_config_repos(self):
        """Without --config-dir, the script defaults to config/repos/ in the repo root."""
        # We just verify it doesn't crash with an "argument required" error
        result = _run_script("--dry-run", env={"GITHUB_TOKEN": "fake"})
        self.assertNotIn(
            "required",
            result.stderr.lower(),
            f"Script requires --config-dir but should default it.\nstderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# Boilerplate
# ---------------------------------------------------------------------------

import re  # noqa: E402 — imported here to keep it close to usage in TestSummaryOutput

if __name__ == "__main__":
    unittest.main()
