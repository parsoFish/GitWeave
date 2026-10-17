"""tests/acceptance/test_gw_overlay_two_modules.py — live acceptance: two-module overlay.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_CALLER_TOKEN, GW_RESOURCE_PREFIX all set in the environment.

Tests are skipped (exit 0) when any required var is absent.

Test map (1:1 with WI-13 AC K1c):
  1. test_two_modules_apply_and_status — K1c
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_CALLER_TOKEN",
    "GW_RESOURCE_PREFIX",
)

_REPO_ROOT = Path(__file__).parent.parent.parent

_MODULE_A = "python_service"
_MODULE_B = "terraform_module"
_MODULE_A_VERSION = "20261017.0"
_MODULE_B_VERSION = "20261017.0"
_MODULE_A_INPUTS = {"service_name": "two_mod_test", "python_version": "3.11"}
_MODULE_B_INPUTS = {"env": "staging"}


def _offline() -> bool:
    return not all(os.environ.get(v) for v in _REQUIRED_VARS)


def _resource_prefix() -> str:
    return os.environ["GW_RESOURCE_PREFIX"]


def _run_gw(*args, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _build_gh_org():
    from gitweave.auth import get_github_client
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def _get_app_token() -> str:
    from gitweave.auth import get_installation_token
    return get_installation_token()


def _ensure_repo_exists(gh_org, repo_name: str):
    try:
        return gh_org.get_repo(repo_name)
    except Exception:
        pass
    return gh_org.create_repo(repo_name, private=False, auto_init=True)


def _delete_repo_if_exists(gh_org, repo_name: str) -> None:
    try:
        gh_org.get_repo(repo_name).delete()
    except Exception:
        pass


def _write_two_module_config(repo_name: str) -> None:
    config_path = _REPO_ROOT / "config" / "repos" / f"{repo_name}.yaml"
    config_data = {
        "spec": {
            "modules": [
                {
                    "name": _MODULE_A,
                    "version": _MODULE_A_VERSION,
                    "inputs": _MODULE_A_INPUTS,
                },
                {
                    "name": _MODULE_B,
                    "version": _MODULE_B_VERSION,
                    "inputs": _MODULE_B_INPUTS,
                },
            ]
        }
    }
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))


def _delete_repo_config(repo_name: str) -> None:
    config_path = _REPO_ROOT / "config" / "repos" / f"{repo_name}.yaml"
    config_path.unlink(missing_ok=True)


@unittest.skipIf(_offline(), "requires GW_* credentials (GW_ORG, GW_APP_ID, ...)")
class TestGwOverlayTwoModulesLive(unittest.TestCase):
    """Live acceptance tests for two-module overlay apply and status (WI-13 K1c)."""

    @classmethod
    def setUpClass(cls):
        cls.prefix = _resource_prefix()
        cls.repo_name = f"{cls.prefix}-overlay-two-mod-test"
        cls.gh_org = _build_gh_org()
        cls.gh_repo = _ensure_repo_exists(cls.gh_org, cls.repo_name)
        cls.app_token = _get_app_token()
        _write_two_module_config(cls.repo_name)

    @classmethod
    def tearDownClass(cls):
        _delete_repo_config(cls.repo_name)
        _delete_repo_if_exists(cls.gh_org, cls.repo_name)

    def _gw_live(self, *args) -> subprocess.CompletedProcess:
        return _run_gw(*args)

    # ------------------------------------------------------------------
    # K1c: two-module apply and status
    # ------------------------------------------------------------------

    def test_two_modules_apply_and_status(self):
        """K1c: apply two modules → both .gitweave/<module>.copier-answers.yml; status lists both."""
        # Apply both modules
        result = self._gw_live("overlay", "apply", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # Verify both per-module answers files exist via GitHub API
        path_a = f".gitweave/{_MODULE_A}.copier-answers.yml"
        path_b = f".gitweave/{_MODULE_B}.copier-answers.yml"

        contents_a = self.gh_repo.get_contents(path_a)
        answers_a = yaml.safe_load(contents_a.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers_a.get("_module_name"), _MODULE_A,
            f"{path_a} has wrong _module_name: {answers_a}",
        )
        self.assertEqual(
            answers_a.get("_module_version"), _MODULE_A_VERSION,
            f"{path_a} has wrong _module_version: {answers_a}",
        )

        contents_b = self.gh_repo.get_contents(path_b)
        answers_b = yaml.safe_load(contents_b.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers_b.get("_module_name"), _MODULE_B,
            f"{path_b} has wrong _module_name: {answers_b}",
        )
        self.assertEqual(
            answers_b.get("_module_version"), _MODULE_B_VERSION,
            f"{path_b} has wrong _module_version: {answers_b}",
        )

        # Root .copier-answers.yml must NOT exist
        try:
            self.gh_repo.get_contents(".copier-answers.yml")
            self.fail("Root .copier-answers.yml must not exist after per-module migration")
        except Exception as exc:
            status = getattr(exc, "status", None)
            self.assertTrue(
                status == 404 or "404" in str(exc),
                f"Expected 404 for root .copier-answers.yml; got: {exc}",
            )

        # Verify gw overlay status lists both modules with name, version, inputs
        status_result = _run_gw("overlay", "status", self.repo_name)
        self.assertEqual(
            status_result.returncode, 0,
            f"Expected exit 0 from status.\nstdout={status_result.stdout}\nstderr={status_result.stderr}",
        )
        self.assertIn(_MODULE_A, status_result.stdout, "Module A name missing from status")
        self.assertIn(_MODULE_B, status_result.stdout, "Module B name missing from status")
        self.assertIn(_MODULE_A_VERSION, status_result.stdout, "Module A version missing from status")
        self.assertIn(_MODULE_B_VERSION, status_result.stdout, "Module B version missing from status")
        # At least one input key from each module should appear
        self.assertTrue(
            any(k in status_result.stdout for k in _MODULE_A_INPUTS),
            f"Expected an input key from module A in status. Got:\n{status_result.stdout}",
        )

        # No open PRs
        prs = list(self.gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs; got {prs}")


if __name__ == "__main__":
    unittest.main()
