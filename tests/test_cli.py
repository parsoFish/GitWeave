"""tests/test_cli.py — CLI integration tests (no live network)."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_env(**overrides):
    """Return os.environ copy stripped of GW_* / FORGE_* with overrides applied."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GW_") and not k.startswith("FORGE_")}
    env.update(overrides)
    return env


def _subprocess_run(*args, env=None):
    """Run `python -m gitweave.cli <args>` as a subprocess."""
    base = _clean_env()
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
        env=base,
    )


def _invoke_main(argv, env_overrides=None):
    """Invoke main() in-process with controlled sys.argv and env.

    Returns (exit_code: int, stdout: str).
    """
    env = _clean_env(**(env_overrides or {}))
    buf = io.StringIO()
    exit_code = 0
    with redirect_stdout(buf), patch("sys.argv", ["gw", *argv]), \
            patch.dict(os.environ, env, clear=True):
        try:
            from gitweave.cli import main
            main()
        except SystemExit as exc:
            exit_code = exc.code if exc.code is not None else 0
    return exit_code, buf.getvalue()


# ---------------------------------------------------------------------------
# AC6: --help
# ---------------------------------------------------------------------------

class TestHelp(unittest.TestCase):
    def test_help_exits_zero(self):
        result = _subprocess_run("--help")
        self.assertEqual(result.returncode, 0)

    def test_help_mentions_all_verbs(self):
        result = _subprocess_run("--help")
        for verb in ("plan", "apply", "reset", "org"):
            self.assertIn(verb, result.stdout, f"verb '{verb}' missing from --help")


# ---------------------------------------------------------------------------
# AC1: plan without --fixture and GW_ORG unset → non-zero, stderr has GW_ORG
# ---------------------------------------------------------------------------

class TestPlanNoOrg(unittest.TestCase):
    def test_plan_without_fixture_and_no_gw_org(self):
        result = _subprocess_run("plan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GW_ORG", result.stderr)


# ---------------------------------------------------------------------------
# AC2: plan --fixture org-empty.json → exit 0, stdout has '+'
# ---------------------------------------------------------------------------

class TestPlanFixture(unittest.TestCase):
    def test_plan_fixture_exits_zero_with_create_lines(self):
        result = _subprocess_run("plan", "--fixture", "tests/fixtures/org-empty.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("+", result.stdout)


# ---------------------------------------------------------------------------
# AC3: apply --json → exit 0, valid JSON with statuses + state
# ---------------------------------------------------------------------------

class TestApplyJson(unittest.TestCase):
    def test_apply_json_structure(self):
        from gitweave.apply import ApplyResult
        from gitweave.managers.org import ResourceStatus

        mock_result = ApplyResult(
            statuses=[ResourceStatus(name="org_settings", status="ok")],
            state={"org_settings": {}},
        )
        mock_gh = MagicMock()
        mock_gh.get_organization.return_value = MagicMock()

        with patch("gitweave.cli.get_github_client", return_value=mock_gh), \
                patch("gitweave.cli.apply", return_value=mock_result):
            exit_code, output = _invoke_main(
                ["apply", "--json"],
                env_overrides={"GW_ORG": "test-org", "FORGE_RESOURCE_PREFIX": "test-"},
            )

        self.assertEqual(exit_code, 0, f"output={output!r}")
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail(f"stdout not valid JSON: {output!r}")
        self.assertIn("statuses", data)
        self.assertIn("state", data)


# ---------------------------------------------------------------------------
# AC4: reset → exit 0
# ---------------------------------------------------------------------------

class TestReset(unittest.TestCase):
    def test_reset_exits_zero(self):
        from gitweave.reset import ResetResult

        mock_result = ResetResult(statuses=[], nothing_changed=True)
        mock_gh = MagicMock()
        mock_gh.get_organization.return_value = MagicMock()

        with patch("gitweave.cli.get_github_client", return_value=mock_gh), \
                patch("gitweave.cli.reset", return_value=mock_result):
            exit_code, _output = _invoke_main(
                ["reset"],
                env_overrides={"GW_ORG": "test-org", "FORGE_RESOURCE_PREFIX": "test-"},
            )

        self.assertEqual(exit_code, 0)


# ---------------------------------------------------------------------------
# AC5: org show --json → exit 0, valid JSON
# ---------------------------------------------------------------------------

class TestOrgShowJson(unittest.TestCase):
    def test_org_show_json(self):
        mock_current = {"description": "", "default_repository_permission": "read"}
        mock_mgr = MagicMock()
        mock_mgr.current.return_value = mock_current

        mock_gh = MagicMock()
        mock_gh.get_organization.return_value = MagicMock()

        with patch("gitweave.cli.get_github_client", return_value=mock_gh), \
                patch("gitweave.managers.org.OrgSettingsManager", return_value=mock_mgr):
            # patch the import inside cmd_org_show
            with patch.dict("sys.modules", {}):
                import gitweave.managers.org as org_mod
                original = org_mod.OrgSettingsManager
                org_mod.OrgSettingsManager = lambda _: mock_mgr
                try:
                    exit_code, output = _invoke_main(
                        ["org", "show", "--json"],
                        env_overrides={"GW_ORG": "test-org", "FORGE_RESOURCE_PREFIX": "test-"},
                    )
                finally:
                    org_mod.OrgSettingsManager = original

        self.assertEqual(exit_code, 0, f"output={output!r}")
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail(f"stdout not valid JSON: {output!r}")
        self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()
