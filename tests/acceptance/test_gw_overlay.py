"""tests/acceptance/test_gw_overlay.py — live acceptance: gw overlay commands.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_CALLER_TOKEN, GW_RESOURCE_PREFIX all set in the environment.

Tests are skipped (exit 0) when any required var is absent.

Test map (1:1 with ACs):
  1. test_overlay_apply_create_branch_live      — AC1
  2. test_overlay_apply_unchanged_branch_live   — AC2
  3. test_overlay_apply_update_inputs_live      — AC3
  4. test_overlay_status_live                   — AC4
  5. test_overlay_request_allowed_and_denied_live — AC5
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_CALLER_TOKEN",
    "GW_RESOURCE_PREFIX",
)

_REPO_ROOT = Path(__file__).parent.parent.parent

_MODULE_NAME = "python_service"
_MODULE_VERSION = "20261017.0"
_MODULE_INPUTS_INITIAL = {"service_name": "overlay_test", "python_version": "3.11"}
_MODULE_INPUTS_UPDATED = {"service_name": "overlay_updated", "python_version": "3.12"}

# Policy team that allows python_service but not terraform_module (per config/policy.yaml)
_TEST_TEAM = "example-team"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _offline() -> bool:
    return not all(os.environ.get(v) for v in _REQUIRED_VARS)


def _resource_prefix() -> str:
    return os.environ["GW_RESOURCE_PREFIX"]


def _run_gw(*args, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run gw via sys.executable."""
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
    """Return GitHub App installation access token."""
    from gitweave.auth import get_installation_token
    return get_installation_token()


def _ensure_repo_exists(gh_org, repo_name: str):
    """Return existing repo or create a new one with auto_init=True."""
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


def _delete_file_on_default_branch(gh_repo, path: str) -> None:
    """Delete *path* on default branch if it exists; silently skip otherwise."""
    try:
        contents = gh_repo.get_contents(path)
        gh_repo.delete_file(path, f"test: remove {path}", contents.sha)
    except Exception:
        pass


def _write_repo_overlay_config(repo_name: str, inputs: dict) -> None:
    """Write config/repos/{repo_name}.yaml with python_service module entry."""
    config_path = _REPO_ROOT / "config" / "repos" / f"{repo_name}.yaml"
    config_data = {
        "spec": {
            "modules": [
                {
                    "name": _MODULE_NAME,
                    "version": _MODULE_VERSION,
                    "inputs": inputs,
                }
            ]
        }
    }
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))


def _delete_repo_overlay_config(repo_name: str) -> None:
    config_path = _REPO_ROOT / "config" / "repos" / f"{repo_name}.yaml"
    config_path.unlink(missing_ok=True)


def _get_default_branch_sha(gh_org, repo_name: str) -> str:
    repo = gh_org.get_repo(repo_name)
    branch = repo.get_branch(repo.default_branch)
    return branch.commit.sha


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@unittest.skipIf(_offline(), "requires GW_* credentials (GW_ORG, GW_APP_ID, ...)")
class TestGwOverlayAcceptance(unittest.TestCase):
    """Live acceptance tests for gw overlay subcommands.

    Tests run in alphabetical order; each builds on the state left by the
    previous one (AC1 → AC2 → AC3 → AC4/AC5 are independent of each other).
    """

    @classmethod
    def setUpClass(cls):
        cls.prefix = _resource_prefix()
        cls.repo_name = f"{cls.prefix}-overlay-test"
        cls.gh_org = _build_gh_org()
        cls.gh_repo = _ensure_repo_exists(cls.gh_org, cls.repo_name)
        cls.app_token = _get_app_token()
        # Write initial overlay config for this repo
        _write_repo_overlay_config(cls.repo_name, _MODULE_INPUTS_INITIAL)

    @classmethod
    def tearDownClass(cls):
        _delete_repo_overlay_config(cls.repo_name)
        _delete_repo_if_exists(cls.gh_org, cls.repo_name)

    def _gw_live(self, *args) -> subprocess.CompletedProcess:
        """Run gw with GW_TOKEN set to the app installation token."""
        return _run_gw(*args, extra_env={"GW_TOKEN": self.app_token})

    # ------------------------------------------------------------------
    # AC1: fresh apply creates .copier-answers.yml; no PR
    # ------------------------------------------------------------------

    def test_overlay_apply_create_branch_live(self):
        """AC1: gw overlay apply on a clean repo creates .gitweave/<module>.copier-answers.yml."""
        _per_module_path = f".gitweave/{_MODULE_NAME}.copier-answers.yml"
        # Clean state: remove per-module answers file if it exists from a prior run
        _delete_file_on_default_branch(self.gh_repo, _per_module_path)

        result = self._gw_live("overlay", "apply", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # Verify per-module answers file via GitHub API GET
        contents = self.gh_repo.get_contents(_per_module_path)
        answers = yaml.safe_load(contents.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers.get("_module_name"), _MODULE_NAME,
            f"{_per_module_path} has wrong _module_name: {answers}",
        )

        # Transport must have sent zero POST .../pulls
        prs = list(self.gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs; got {prs}")

    # ------------------------------------------------------------------
    # AC2: second apply with same inputs leaves HEAD unchanged
    # ------------------------------------------------------------------

    def test_overlay_apply_unchanged_branch_live(self):
        """AC2: repeat apply with same inputs leaves HEAD SHA unchanged."""
        sha_before = _get_default_branch_sha(self.gh_org, self.repo_name)

        result = self._gw_live("overlay", "apply", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        sha_after = _get_default_branch_sha(self.gh_org, self.repo_name)
        self.assertEqual(
            sha_before, sha_after,
            "Expected HEAD SHA unchanged on second apply with same inputs.",
        )

    # ------------------------------------------------------------------
    # AC3: apply with updated inputs creates new commit; no PR
    # ------------------------------------------------------------------

    def test_overlay_apply_update_inputs_live(self):
        """AC3: apply with different inputs creates a new commit; no PR."""
        # Update config to new inputs
        _write_repo_overlay_config(self.repo_name, _MODULE_INPUTS_UPDATED)

        sha_before = _get_default_branch_sha(self.gh_org, self.repo_name)

        result = self._gw_live("overlay", "apply", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        sha_after = _get_default_branch_sha(self.gh_org, self.repo_name)
        self.assertNotEqual(
            sha_before, sha_after,
            "Expected new commit after input change.",
        )

        # Verify per-module answers file reflects updated inputs
        _per_module_path = f".gitweave/{_MODULE_NAME}.copier-answers.yml"
        contents = self.gh_repo.get_contents(_per_module_path)
        answers = yaml.safe_load(contents.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers.get("_answers", {}).get("service_name"),
            _MODULE_INPUTS_UPDATED["service_name"],
            f"Expected updated service_name in {_per_module_path}; got {answers}",
        )

        # No open PRs
        prs = list(self.gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs; got {prs}")

    # ------------------------------------------------------------------
    # AC4: overlay status prints module name, version, inputs
    # ------------------------------------------------------------------

    def test_overlay_status_live(self):
        """AC4: gw overlay status prints module name, version, and input keys."""
        result = _run_gw("overlay", "status", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn(_MODULE_NAME, result.stdout, "Module name missing from status output.")
        self.assertIn(_MODULE_VERSION, result.stdout, "Module version missing from status output.")
        # At least one input key should appear
        self.assertTrue(
            any(k in result.stdout for k in _MODULE_INPUTS_UPDATED),
            f"Expected an input key in status output. Got:\n{result.stdout}",
        )

    # ------------------------------------------------------------------
    # AC5: allowed module applies; denied module refused with policy rule
    # ------------------------------------------------------------------

    def test_overlay_request_allowed_and_denied_live(self):
        """AC5: allowed module request succeeds; denied module fails with policy rule name."""
        # Allowed: python_service (example-team policy allows it)
        result_allow = self._gw_live(
            "overlay", "request",
            "--team", _TEST_TEAM,
            "--repo", self.repo_name,
            "--module", _MODULE_NAME,
        )
        self.assertEqual(
            result_allow.returncode, 0,
            f"Expected exit 0 for allowed module '{_MODULE_NAME}'.\n"
            f"stdout={result_allow.stdout}\nstderr={result_allow.stderr}",
        )
        # No open PRs after allowed request
        prs = list(self.gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs after allowed request; got {prs}")

        # Denied: terraform_module (not in example-team allowed_modules)
        result_deny = self._gw_live(
            "overlay", "request",
            "--team", _TEST_TEAM,
            "--repo", self.repo_name,
            "--module", "terraform_module",
        )
        self.assertNotEqual(
            result_deny.returncode, 0,
            "Expected non-zero exit for denied module 'terraform_module'.",
        )
        # Policy rule name must appear in stderr
        self.assertIn(
            "allowed_modules",
            result_deny.stderr,
            f"Expected policy rule name 'allowed_modules' in stderr.\nGot: {result_deny.stderr}",
        )
        # Zero write calls after refusal: verify no new PRs
        prs_after = list(self.gh_repo.get_pulls(state="open"))
        self.assertEqual(
            prs_after, [],
            f"Expected zero open PRs after denied request; got {prs_after}",
        )
