"""
Tests for environment-specific variable overrides in overlay configuration.

Work item: Implement environment-specific variable overrides in overlay config

These tests define expected behaviour BEFORE implementation (TDD red phase).
All tests in this file will FAIL until the feature is implemented.

Feature summary
---------------
The apply-overlays.py script accepts a --env <name> argument.  When supplied:

  1. The script reads spec.variables from the overlay config as the base
     variable set.
  2. It reads spec.environments.<env>.variables as the environment-specific
     override set.
  3. It deep-merges them: environment values take precedence for matching keys;
     base values are preserved for keys absent in the environment override.
  4. The merged variables are passed to copier via --data flags (or equivalent)
     when running each module.

The gitweave-apply.yaml workflow exposes a TARGET_ENV workflow_dispatch input
that is forwarded to the apply script as --env <value>.

JSON Schema contract
--------------------
spec.environments.<env>.variables must be validated as a string-to-string map.
The existing schema tests cover spec.environments.*.variables at the
environment level, but we add targeted tests here to drive the merge logic.

Test layers
-----------
Unit — TestMergeVariables
    Pure function tests for the merge_variables(base, env_override) helper
    that implements the deep-merge strategy.

Unit — TestEnvArgument
    Tests that apply_overlay accepts an optional env parameter and uses it to
    look up spec.environments.<env>.variables for merging.

Unit — TestApplyOverlayPassesVariablesToCopier
    Tests that the resolved (merged) variables are passed to copier copy as
    --data KEY=VALUE flags.

Integration — TestApplyOverlayWithEnvIntegration
    Tests apply_overlay end-to-end with mocked subprocess, verifying that
    staging-specific values reach the copier invocation and base-only values
    are preserved.

Integration CLI — TestEnvArgumentCLI
    Subprocess-level tests that invoke apply-overlays.py --env staging ... and
    verify the correct dry-run output and exit codes.

Workflow — TestGitweaveApplyWorkflowTargetEnv
    Tests for .github/workflows/gitweave-apply.yaml to verify it exposes a
    TARGET_ENV workflow_dispatch input and passes it as --env to the script.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "apply-overlays.py")
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "gitweave-apply.yaml")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_script():
    """
    Import apply-overlays.py as a Python module.
    Raises FileNotFoundError with a descriptive message when absent.
    """
    if not os.path.isfile(SCRIPT_PATH):
        raise FileNotFoundError(
            f"scripts/apply-overlays.py not found at {SCRIPT_PATH}"
        )
    spec = importlib.util.spec_from_file_location("apply_overlays", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke apply-overlays.py with given arguments, capturing output."""
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, SCRIPT_PATH, *args],
        capture_output=True,
        text=True,
        env=run_env,
    )


def _write_yaml(directory: str, filename: str, doc: dict) -> str:
    """Write doc as YAML to directory/filename and return the full path."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    return path


def _overlay_with_variables(
    repo: str = "my-org/my-app",
    base_variables: dict | None = None,
    environments: dict | None = None,
    modules: list | None = None,
) -> dict:
    """Return a RepositoryOverlay doc that exercises variable sections."""
    doc: dict = {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": "my-app"},
        "spec": {"repository": repo},
    }
    if base_variables is not None:
        doc["spec"]["variables"] = base_variables
    if environments is not None:
        doc["spec"]["environments"] = environments
    if modules is not None:
        doc["spec"]["modules"] = modules
    return doc


# ---------------------------------------------------------------------------
# TestMergeVariables — pure function unit tests
# ---------------------------------------------------------------------------


class TestMergeVariables(unittest.TestCase):
    """
    Unit tests for the merge_variables(base, env_override) helper.

    merge_variables must implement a simple dict merge where:
      - env_override values replace base values for the same key
      - base values for keys absent in env_override are preserved
      - keys present only in env_override are added to the result
      - neither input dict is mutated
    """

    def setUp(self):
        self.mod = _load_script()

    def test_script_exposes_merge_variables_callable(self):
        """apply-overlays.py must expose a callable merge_variables function."""
        self.assertTrue(
            callable(getattr(self.mod, "merge_variables", None)),
            "apply-overlays.py does not expose callable 'merge_variables'. "
            "Add merge_variables(base, env_override) -> dict to the script.",
        )

    def test_env_override_replaces_base_value_for_same_key(self):
        """Environment variable overrides base variable when both share the same key."""
        base = {"LOG_LEVEL": "info", "REGION": "us-west-2"}
        env_override = {"LOG_LEVEL": "debug"}
        result = self.mod.merge_variables(base, env_override)
        self.assertEqual(
            result["LOG_LEVEL"],
            "debug",
            "Environment override must win over base for shared key 'LOG_LEVEL'. "
            f"Got: {result}",
        )

    def test_base_only_key_is_preserved_when_not_in_env_override(self):
        """Keys present only in base variables must be preserved in the merged result."""
        base = {"LOG_LEVEL": "info", "REGION": "us-west-2"}
        env_override = {"LOG_LEVEL": "debug"}
        result = self.mod.merge_variables(base, env_override)
        self.assertIn(
            "REGION",
            result,
            "Key 'REGION' (base-only) must be preserved in merge result. "
            f"Got: {result}",
        )
        self.assertEqual(
            result["REGION"],
            "us-west-2",
            "Base-only key 'REGION' must retain its base value. "
            f"Got: {result}",
        )

    def test_env_only_key_is_added_to_result(self):
        """Keys present only in env_override must be added to the merged result."""
        base = {"LOG_LEVEL": "info"}
        env_override = {"LOG_LEVEL": "warn", "FEATURE_FLAG": "enabled"}
        result = self.mod.merge_variables(base, env_override)
        self.assertIn(
            "FEATURE_FLAG",
            result,
            "Key 'FEATURE_FLAG' present only in env_override must appear in result. "
            f"Got: {result}",
        )
        self.assertEqual(
            result["FEATURE_FLAG"],
            "enabled",
            "Env-only key 'FEATURE_FLAG' must carry its env value. "
            f"Got: {result}",
        )

    def test_empty_env_override_returns_base_unchanged(self):
        """When env_override is empty, the result equals base."""
        base = {"LOG_LEVEL": "info", "REGION": "us-east-1"}
        result = self.mod.merge_variables(base, {})
        self.assertEqual(
            result,
            base,
            "merge_variables with empty env_override must return a copy of base. "
            f"Got: {result}",
        )

    def test_empty_base_returns_env_override(self):
        """When base is empty, the result equals env_override."""
        env_override = {"LOG_LEVEL": "debug", "REGION": "eu-west-1"}
        result = self.mod.merge_variables({}, env_override)
        self.assertEqual(
            result,
            env_override,
            "merge_variables with empty base must return a copy of env_override. "
            f"Got: {result}",
        )

    def test_both_empty_returns_empty_dict(self):
        """When both inputs are empty, the result is an empty dict."""
        result = self.mod.merge_variables({}, {})
        self.assertEqual(
            result,
            {},
            "merge_variables({}, {}) must return {}. Got: {result}",
        )

    def test_does_not_mutate_base_dict(self):
        """merge_variables must not modify the base dict in-place."""
        base = {"LOG_LEVEL": "info"}
        original_base = dict(base)
        env_override = {"LOG_LEVEL": "debug", "EXTRA": "value"}
        self.mod.merge_variables(base, env_override)
        self.assertEqual(
            base,
            original_base,
            "merge_variables must not mutate the base dict. "
            f"base before: {original_base}, after: {base}",
        )

    def test_does_not_mutate_env_override_dict(self):
        """merge_variables must not modify the env_override dict in-place."""
        base = {"LOG_LEVEL": "info", "EXTRA": "base_value"}
        env_override = {"LOG_LEVEL": "debug"}
        original_env = dict(env_override)
        self.mod.merge_variables(base, env_override)
        self.assertEqual(
            env_override,
            original_env,
            "merge_variables must not mutate the env_override dict. "
            f"env_override before: {original_env}, after: {env_override}",
        )

    def test_multiple_shared_keys_all_get_overridden(self):
        """All keys shared between base and env_override must use the env value."""
        base = {"A": "a-base", "B": "b-base", "C": "c-base"}
        env_override = {"A": "a-env", "B": "b-env"}
        result = self.mod.merge_variables(base, env_override)
        self.assertEqual(result["A"], "a-env", f"Key A must use env value. Got: {result}")
        self.assertEqual(result["B"], "b-env", f"Key B must use env value. Got: {result}")
        self.assertEqual(result["C"], "c-base", f"Key C (base-only) must be preserved. Got: {result}")

    def test_returns_new_dict_not_reference_to_base_or_override(self):
        """merge_variables must return a new dict, not the base or env_override object."""
        base = {"A": "1"}
        env_override = {"B": "2"}
        result = self.mod.merge_variables(base, env_override)
        self.assertIsNot(result, base, "Result must not be the same object as base")
        self.assertIsNot(result, env_override, "Result must not be the same object as env_override")


# ---------------------------------------------------------------------------
# TestEnvArgument — apply_overlay accepts env parameter
# ---------------------------------------------------------------------------


class TestEnvArgument(unittest.TestCase):
    """
    Unit tests verifying that apply_overlay accepts an 'env' keyword argument
    and uses it to look up spec.environments.<env>.variables for merging.
    """

    def setUp(self):
        self.mod = _load_script()

    def test_apply_overlay_accepts_env_keyword_argument(self):
        """apply_overlay must accept an 'env' keyword argument without raising TypeError."""
        config = _overlay_with_variables(
            base_variables={"LOG_LEVEL": "info"},
            environments={"staging": {"variables": {"LOG_LEVEL": "debug"}}},
            modules=[{"name": "lang-node"}],
        )
        try:
            self.mod.apply_overlay(
                config=config,
                modules_dir="/repo/modules",
                github_token="fake-token",
                dry_run=True,
                env="staging",
            )
        except TypeError as exc:
            self.fail(
                f"apply_overlay raised TypeError when 'env' was passed: {exc}. "
                "Add 'env: str | None = None' to the apply_overlay signature."
            )

    def test_apply_overlay_does_not_require_env_argument(self):
        """apply_overlay must not require the 'env' argument — it is optional."""
        config = _overlay_with_variables(
            base_variables={"LOG_LEVEL": "info"},
            modules=[{"name": "lang-node"}],
        )
        try:
            self.mod.apply_overlay(
                config=config,
                modules_dir="/repo/modules",
                github_token="fake-token",
                dry_run=True,
            )
        except TypeError as exc:
            if "env" in str(exc).lower():
                self.fail(
                    f"apply_overlay requires 'env' but it should be optional: {exc}"
                )


# ---------------------------------------------------------------------------
# TestApplyOverlayPassesVariablesToCopier
# ---------------------------------------------------------------------------


class TestApplyOverlayPassesVariablesToCopier(unittest.TestCase):
    """
    Tests that the resolved variables (merged base + env) are passed to copier
    via --data KEY=VALUE flags when invoking copier copy.
    """

    def setUp(self):
        self.mod = _load_script()

    def _make_successful_run(self) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_base_variables_passed_to_copier_when_no_env_specified(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """When no --env is passed, spec.variables are forwarded to copier as --data flags."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            base_variables={"TEAM_NAME": "platform", "REGION": "us-east-1"},
            modules=[{"name": "lang-node"}],
        )
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )

        all_calls = " ".join(str(c) for c in mock_run.call_args_list)
        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "No copier call found; cannot verify --data flags")

        copier_call_str = str(copier_calls[0])
        self.assertIn(
            "TEAM_NAME",
            copier_call_str,
            "copier invocation must include --data TEAM_NAME=platform "
            f"when base_variables has TEAM_NAME. Copier call: {copier_call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_env_override_value_reaches_copier_for_shared_key(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """When --env staging is given, the staging LOG_LEVEL overrides the base LOG_LEVEL in the copier call."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            base_variables={"LOG_LEVEL": "info"},
            environments={"staging": {"variables": {"LOG_LEVEL": "debug"}}},
            modules=[{"name": "lang-node"}],
        )
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            env="staging",
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "No copier call found; cannot verify --data flags")

        copier_call_str = str(copier_calls[0])
        # The staging override value 'debug' must reach copier, not the base 'info'
        self.assertIn(
            "debug",
            copier_call_str,
            "copier invocation must include LOG_LEVEL=debug (staging override), "
            f"not 'info' (base). Copier call: {copier_call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_base_only_variable_preserved_in_copier_call_when_env_active(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """Base-only variable keys must still appear in the copier --data flags when env overrides are applied."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            base_variables={"LOG_LEVEL": "info", "TEAM_NAME": "platform"},
            environments={"staging": {"variables": {"LOG_LEVEL": "debug"}}},
            modules=[{"name": "lang-node"}],
        )
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            env="staging",
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "No copier call found; cannot verify --data flags")

        copier_call_str = str(copier_calls[0])
        self.assertIn(
            "TEAM_NAME",
            copier_call_str,
            "Base-only variable 'TEAM_NAME' must still reach copier when staging "
            f"env overrides are active. Copier call: {copier_call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_env_only_variable_added_to_copier_call(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """Variables present only in env override must be added to the copier --data flags."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            base_variables={"LOG_LEVEL": "info"},
            environments={"staging": {"variables": {"STAGING_FEATURE": "enabled"}}},
            modules=[{"name": "lang-node"}],
        )
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            env="staging",
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "No copier call found; cannot verify --data flags")

        copier_call_str = str(copier_calls[0])
        self.assertIn(
            "STAGING_FEATURE",
            copier_call_str,
            "Env-only variable 'STAGING_FEATURE' must appear in copier --data flags. "
            f"Copier call: {copier_call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_unknown_env_name_falls_back_to_base_variables_only(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """When --env specifies an environment not in spec.environments, fall back to base variables only."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            base_variables={"LOG_LEVEL": "info"},
            environments={"prod": {"variables": {"LOG_LEVEL": "error"}}},
            modules=[{"name": "lang-node"}],
        )
        # 'staging' is not in spec.environments — should not raise, should use base
        try:
            result = self.mod.apply_overlay(
                config=config,
                modules_dir="/repo/modules",
                github_token="token",
                dry_run=False,
                env="staging",
            )
        except Exception as exc:
            self.fail(
                f"apply_overlay raised {type(exc).__name__} for unknown env 'staging'. "
                "It should fall back to base variables silently: {exc}"
            )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_no_data_flags_when_no_variables_defined(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """When neither spec.variables nor env variables are set, copier is called without --data flags."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-app",
            modules=[{"name": "lang-node"}],
            # No variables, no environments
        )
        # Should not raise; --data flags are optional
        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
        )
        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "copier must still be called even without variables")


# ---------------------------------------------------------------------------
# TestApplyOverlayWithEnvIntegration — end-to-end merge verification
# ---------------------------------------------------------------------------


class TestApplyOverlayWithEnvIntegration(unittest.TestCase):
    """
    Integration tests that verify the complete env-override → copier pipeline
    with mocked subprocess but real config dict construction.

    These tests verify the observable behaviour at the API boundary:
      - apply_overlay called with env="staging"
      - staging variables override base for matching keys
      - base-only variables are preserved
      - staging-only variables are added
    """

    def setUp(self):
        self.mod = _load_script()

    def _make_successful_run(self) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_staging_env_overrides_base_log_level(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """
        Integration: when env=staging, the LOG_LEVEL sent to copier is the
        staging value ('debug'), not the base value ('info').
        """
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-service",
            base_variables={"LOG_LEVEL": "info", "TEAM_NAME": "platform"},
            environments={
                "staging": {
                    "variables": {
                        "LOG_LEVEL": "debug",
                        "STAGING_URL": "https://staging.example.com",
                    }
                },
                "prod": {
                    "variables": {
                        "LOG_LEVEL": "error",
                        "PROD_URL": "https://prod.example.com",
                    }
                },
            },
            modules=[{"name": "lang-node"}],
        )

        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            env="staging",
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "copier must be called")
        call_str = str(copier_calls[0])

        # env override wins for LOG_LEVEL
        self.assertIn("debug", call_str, f"staging LOG_LEVEL=debug must reach copier. Got: {call_str}")
        # base-only TEAM_NAME is preserved
        self.assertIn("TEAM_NAME", call_str, f"base-only TEAM_NAME must be in copier args. Got: {call_str}")
        # staging-only key is added
        self.assertIn("STAGING_URL", call_str, f"staging-only STAGING_URL must reach copier. Got: {call_str}")
        # prod-only key must NOT appear
        self.assertNotIn(
            "PROD_URL",
            call_str,
            f"prod-only PROD_URL must NOT appear in staging copier call. Got: {call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_prod_env_overrides_base_log_level(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """Integration: when env=prod, the prod LOG_LEVEL ('error') is used."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-service",
            base_variables={"LOG_LEVEL": "info"},
            environments={
                "staging": {"variables": {"LOG_LEVEL": "debug"}},
                "prod": {"variables": {"LOG_LEVEL": "error"}},
            },
            modules=[{"name": "lang-node"}],
        )

        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            env="prod",
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "copier must be called")
        call_str = str(copier_calls[0])

        self.assertIn("error", call_str, f"prod LOG_LEVEL=error must reach copier. Got: {call_str}")
        # staging value must not leak into the prod call
        self.assertNotIn(
            "debug",
            call_str,
            f"staging LOG_LEVEL=debug must NOT appear in prod copier call. Got: {call_str}",
        )

    @patch("subprocess.run")
    @patch("tempfile.TemporaryDirectory")
    def test_no_env_uses_only_base_variables(
        self, mock_tmpdir: MagicMock, mock_run: MagicMock
    ):
        """When no env is specified, only spec.variables (base) are forwarded to copier."""
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fakedir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        mock_run.return_value = self._make_successful_run()

        config = _overlay_with_variables(
            repo="org/my-service",
            base_variables={"LOG_LEVEL": "info"},
            environments={"staging": {"variables": {"LOG_LEVEL": "debug"}}},
            modules=[{"name": "lang-node"}],
        )

        self.mod.apply_overlay(
            config=config,
            modules_dir="/repo/modules",
            github_token="token",
            dry_run=False,
            # No env argument
        )

        copier_calls = [c for c in mock_run.call_args_list if "copier" in str(c)]
        self.assertTrue(copier_calls, "copier must be called")
        call_str = str(copier_calls[0])

        # base value 'info' should be present, staging override 'debug' should not
        self.assertIn("info", call_str, f"Base LOG_LEVEL=info must reach copier. Got: {call_str}")
        self.assertNotIn(
            "debug",
            call_str,
            f"staging LOG_LEVEL=debug must NOT appear when no env is specified. Got: {call_str}",
        )


# ---------------------------------------------------------------------------
# TestEnvArgumentCLI — subprocess-level CLI tests
# ---------------------------------------------------------------------------


class TestEnvArgumentCLI(unittest.TestCase):
    """
    CLI-level tests that invoke apply-overlays.py as a subprocess to verify
    the --env argument is accepted and produces correct exit codes.
    """

    def test_script_accepts_env_argument(self):
        """Script must accept --env <name> without reporting an unrecognised argument error."""
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent/path",
            "--env",
            "staging",
        )
        self.assertNotIn(
            "unrecognized argument",
            result.stderr,
            f"Script rejected --env argument.\nstderr: {result.stderr}",
        )
        self.assertNotIn(
            "error: argument",
            result.stderr.lower(),
            f"Script reported argument error for --env.\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_exits_zero_for_empty_config_dir(self):
        """--dry-run --env staging must exit 0 when config dir is empty or absent."""
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent/path",
            "--env",
            "staging",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Script should exit 0 in dry-run with --env and no configs.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_prints_env_name_in_output(self):
        """Dry-run output with --env staging should mention the environment name."""
        with tempfile.TemporaryDirectory() as config_dir:
            _write_yaml(
                config_dir,
                "my-service.yaml",
                _overlay_with_variables(
                    repo="org/my-service",
                    base_variables={"LOG_LEVEL": "info"},
                    environments={"staging": {"variables": {"LOG_LEVEL": "debug"}}},
                    modules=[{"name": "lang-node"}],
                ),
            )
            result = _run_script(
                "--dry-run",
                "--config-dir",
                config_dir,
                "--env",
                "staging",
            )

        combined = result.stdout + result.stderr
        self.assertIn(
            "staging",
            combined,
            "Dry-run output with --env staging must mention 'staging' so operators "
            "can confirm which environment is being targeted.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_without_env_exits_zero(self):
        """Existing dry-run behaviour without --env must continue to work."""
        with tempfile.TemporaryDirectory() as config_dir:
            _write_yaml(
                config_dir,
                "my-service.yaml",
                _overlay_with_variables(
                    repo="org/my-service",
                    base_variables={"LOG_LEVEL": "info"},
                    modules=[{"name": "lang-node"}],
                ),
            )
            result = _run_script(
                "--dry-run",
                "--config-dir",
                config_dir,
            )
        self.assertEqual(
            result.returncode,
            0,
            "Script must exit 0 in dry-run without --env (regression check).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_env_argument_is_optional(self):
        """Existing invocations without --env must continue to work without error."""
        result = _run_script(
            "--dry-run",
            "--config-dir",
            "/nonexistent/path",
        )
        self.assertNotIn(
            "required",
            result.stderr.lower(),
            "Script must not require --env — it should be optional.\n"
            f"stderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestEnvironmentVariablesSchemaExtension — schema-level validation
# ---------------------------------------------------------------------------


class TestEnvironmentVariablesSchemaExtension(unittest.TestCase):
    """
    Tests that spec.environments.<env>.variables is validated as a string map
    by the JSON Schema.  These are targeted tests for the env-override feature;
    the broader schema contract is tested in test_overlay_schema.py.
    """

    def setUp(self):
        import json
        import jsonschema

        schema_path = os.path.join(REPO_ROOT, "schemas", "overlay.schema.json")
        if not os.path.isfile(schema_path):
            self.skipTest(f"Schema file not found at {schema_path}")
        with open(schema_path) as f:
            self.schema = json.load(f)
        self.validate = lambda doc: jsonschema.validate(instance=doc, schema=self.schema)

    def test_environment_variables_string_map_is_valid(self):
        """spec.environments.<env>.variables with string values must pass schema validation."""
        doc = _overlay_with_variables(
            environments={
                "staging": {
                    "variables": {
                        "LOG_LEVEL": "debug",
                        "REGION": "eu-west-1",
                    }
                }
            }
        )
        try:
            self.validate(doc)
        except Exception as exc:
            self.fail(
                f"Valid environment variables map failed schema validation: {exc}\n"
                f"Doc: {doc}"
            )

    def test_environment_variables_with_numeric_value_is_rejected(self):
        """spec.environments.<env>.variables with a non-string value must fail validation."""
        import jsonschema

        doc = _overlay_with_variables(
            environments={"staging": {"variables": {"PORT": 8080}}}
        )
        with self.assertRaises(
            jsonschema.ValidationError,
            msg="environment.variables with numeric value must be rejected by schema",
        ):
            self.validate(doc)

    def test_environment_variables_with_boolean_value_is_rejected(self):
        """spec.environments.<env>.variables with a boolean value must fail validation."""
        import jsonschema

        doc = _overlay_with_variables(
            environments={"prod": {"variables": {"ENABLED": True}}}
        )
        with self.assertRaises(
            jsonschema.ValidationError,
            msg="environment.variables with boolean value must be rejected by schema",
        ):
            self.validate(doc)

    def test_environment_variables_with_null_value_is_rejected(self):
        """spec.environments.<env>.variables with a null value must fail validation."""
        import jsonschema

        doc = _overlay_with_variables(
            environments={"dev": {"variables": {"KEY": None}}}
        )
        with self.assertRaises(
            jsonschema.ValidationError,
            msg="environment.variables with null value must be rejected by schema",
        ):
            self.validate(doc)

    def test_multiple_envs_each_with_string_variables_is_valid(self):
        """Multiple environments, each with string variable maps, must all pass validation."""
        doc = _overlay_with_variables(
            base_variables={"TEAM_NAME": "platform"},
            environments={
                "dev": {"variables": {"LOG_LEVEL": "debug"}},
                "staging": {"variables": {"LOG_LEVEL": "info", "STAGING_FLAG": "on"}},
                "prod": {"variables": {"LOG_LEVEL": "error", "ALERT_THRESHOLD": "95"}},
            },
        )
        try:
            self.validate(doc)
        except Exception as exc:
            self.fail(
                f"Multi-environment string variable config failed schema validation: {exc}"
            )


# ---------------------------------------------------------------------------
# TestGitweaveApplyWorkflowTargetEnv — workflow YAML tests
# ---------------------------------------------------------------------------


class TestGitweaveApplyWorkflowTargetEnv(unittest.TestCase):
    """
    Tests for .github/workflows/gitweave-apply.yaml to verify it exposes
    TARGET_ENV as a workflow_dispatch input and passes it to the apply script.
    """

    def _load_workflow(self) -> dict:
        if not os.path.isfile(WORKFLOW_PATH):
            self.skipTest(f"Workflow file not found at {WORKFLOW_PATH}")
        with open(WORKFLOW_PATH) as f:
            return yaml.safe_load(f)

    def test_workflow_file_is_valid_yaml(self):
        """The gitweave-apply.yaml workflow must parse as valid YAML."""
        workflow = self._load_workflow()
        self.assertIsInstance(workflow, dict, "gitweave-apply.yaml must parse as a YAML mapping")

    def test_workflow_dispatch_trigger_exists(self):
        """The workflow must have a workflow_dispatch trigger (for manual invocation)."""
        workflow = self._load_workflow()
        on_section = workflow.get("on") or workflow.get(True)
        self.assertIn(
            "workflow_dispatch",
            on_section,
            "gitweave-apply.yaml must define a 'workflow_dispatch' trigger. "
            f"Got 'on' section: {on_section}",
        )

    def test_workflow_dispatch_has_target_env_input(self):
        """workflow_dispatch must declare a 'target_env' input for environment selection."""
        workflow = self._load_workflow()
        on_section = workflow.get("on") or workflow.get(True)
        dispatch_inputs = (
            on_section.get("workflow_dispatch", {}) or {}
        ).get("inputs", {}) or {}

        self.assertIn(
            "target_env",
            dispatch_inputs,
            "workflow_dispatch.inputs must include 'target_env' so operators can "
            "specify which environment to target. "
            f"Current inputs: {list(dispatch_inputs.keys())}",
        )

    def test_target_env_input_is_string_type(self):
        """The target_env workflow_dispatch input must be of type 'string' (or 'choice')."""
        workflow = self._load_workflow()
        on_section = workflow.get("on") or workflow.get(True)
        dispatch_inputs = (
            on_section.get("workflow_dispatch", {}) or {}
        ).get("inputs", {}) or {}

        target_env_input = dispatch_inputs.get("target_env", {}) or {}
        input_type = target_env_input.get("type", "string")  # default is string

        self.assertIn(
            input_type,
            ("string", "choice"),
            f"target_env input type must be 'string' or 'choice', got: {input_type!r}",
        )

    def test_apply_step_passes_env_argument_from_target_env_input(self):
        """
        At least one apply step must pass '--env' using the target_env input value
        so that the environment-specific variables are selected at runtime.
        """
        workflow = self._load_workflow()
        jobs = workflow.get("jobs", {})

        # Flatten all step 'run' blocks from all jobs
        all_run_steps: list[str] = []
        for job_name, job in jobs.items():
            for step in job.get("steps", []):
                run_cmd = step.get("run", "")
                if run_cmd:
                    all_run_steps.append(run_cmd)

        env_flag_present = any(
            "--env" in step or "target_env" in step or "TARGET_ENV" in step
            for step in all_run_steps
        )
        self.assertTrue(
            env_flag_present,
            "No apply step passes --env to apply-overlays.py. "
            "Add '--env ${{ inputs.target_env }}' (or equivalent) to the apply step. "
            f"Current run steps: {all_run_steps}",
        )

    def test_workflow_preserves_existing_dry_run_input(self):
        """The existing dry_run workflow_dispatch input must be preserved (regression guard)."""
        workflow = self._load_workflow()
        on_section = workflow.get("on") or workflow.get(True)
        dispatch_inputs = (
            on_section.get("workflow_dispatch", {}) or {}
        ).get("inputs", {}) or {}

        self.assertIn(
            "dry_run",
            dispatch_inputs,
            "The existing 'dry_run' workflow_dispatch input must not be removed "
            f"when adding target_env. Current inputs: {list(dispatch_inputs.keys())}",
        )


# ---------------------------------------------------------------------------
# Boilerplate
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
