"""tests/acceptance/test_gw_apply_overlay_live.py — live acceptance: gw apply with overlay.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_CALLER_TOKEN, GW_RESOURCE_PREFIX all set in the environment.

Tests are skipped (exit 0) when any required var is absent.

Test map (1:1 with WI-17 AC4):
  1. test_gw_apply_creates_overlay_files      — AC4 first apply
  2. test_gw_apply_idempotent_head_sha        — AC4 second apply leaves SHA unchanged
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
_MODULE_INPUTS = {"service_name": "apply_overlay_test", "python_version": "3.11"}

# Rendered file we expect to find after apply
_EXPECTED_WORKFLOW_PATH = ".github/workflows/ci.yml"
_ANSWERS_PATH = f".gitweave/{_MODULE_NAME}.copier-answers.yml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _offline() -> bool:
    return not all(os.environ.get(v) for v in _REQUIRED_VARS)


def _resource_prefix() -> str:
    return os.environ["GW_RESOURCE_PREFIX"]


def _run_gw(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def _build_gh_org():
    from gitweave.auth import get_github_client
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def _get_app_token() -> str:
    from gitweave.auth import get_installation_token
    return get_installation_token()


def _create_empty_repo(gh_org, repo_name: str):
    """Create a repository with NO initial commit (auto_init=False)."""
    try:
        existing = gh_org.get_repo(repo_name)
        existing.delete()
    except Exception:
        pass
    return gh_org.create_repo(repo_name, private=False, auto_init=False)


def _delete_repo_if_exists(gh_org, repo_name: str) -> None:
    try:
        gh_org.get_repo(repo_name).delete()
    except Exception:
        pass


def _write_overlay_config(repo_name: str, inputs: dict) -> Path:
    """Write config/repos/{repo_name}.yaml as an overlay config (with apiVersion)."""
    config_path = _REPO_ROOT / "config" / "repos" / f"{repo_name}.yaml"
    config_data = {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo_name},
        "spec": {
            "repository": f"{os.environ['GW_ORG']}/{repo_name}",
            "modules": [
                {
                    "name": _MODULE_NAME,
                    "version": _MODULE_VERSION,
                    "inputs": inputs,
                }
            ],
        },
    }
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))
    return config_path


def _delete_overlay_config(repo_name: str) -> None:
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
class TestGwApplyOverlayLive(unittest.TestCase):
    """Live acceptance: gw apply with an overlay repo config.

    Creates a throwaway empty repo, declares it as an overlay repo in a
    temporary config/repos/<name>.yaml, runs `gw apply` as a subprocess,
    verifies the rendered files are present on the default branch (reading
    content back through the API with the installation token), then asserts
    a second `gw apply` leaves the head SHA unchanged.
    """

    @classmethod
    def setUpClass(cls):
        cls.prefix = _resource_prefix()
        cls.repo_name = f"{cls.prefix}-gw-apply-overlay-test"
        cls.gh_org = _build_gh_org()
        cls.app_token = _get_app_token()
        # Create empty repo (no commits)
        cls.gh_repo = _create_empty_repo(cls.gh_org, cls.repo_name)
        # Write overlay config so load_config() picks it up under overlay_repos
        _write_overlay_config(cls.repo_name, _MODULE_INPUTS)

    @classmethod
    def tearDownClass(cls):
        _delete_overlay_config(cls.repo_name)
        _delete_repo_if_exists(cls.gh_org, cls.repo_name)

    # ------------------------------------------------------------------
    # AC4-a: first gw apply writes module files and answers file
    # ------------------------------------------------------------------

    def test_gw_apply_creates_overlay_files(self):
        """AC4: gw apply on an overlay repo writes ci.yml and answers file."""
        result = _run_gw("apply")
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # Reload repo to pick up the newly created default branch
        gh_repo = self.gh_org.get_repo(self.repo_name)

        # --- read back .github/workflows/ci.yml content via API ---
        try:
            ci_contents = gh_repo.get_contents(_EXPECTED_WORKFLOW_PATH)
        except Exception as exc:
            self.fail(
                f"{_EXPECTED_WORKFLOW_PATH!r} not found after gw apply: {exc}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        ci_text = ci_contents.decoded_content.decode("utf-8")
        self.assertIn(
            "on:",
            ci_text,
            f"ci.yml content looks wrong: {ci_text[:200]}",
        )

        # --- read back module answers file via API ---
        try:
            answers_contents = gh_repo.get_contents(_ANSWERS_PATH)
        except Exception as exc:
            self.fail(
                f"{_ANSWERS_PATH!r} not found after gw apply: {exc}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        answers = yaml.safe_load(answers_contents.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers.get("_module_name"),
            _MODULE_NAME,
            f"Expected _module_name={_MODULE_NAME!r}; got {answers}",
        )

        # --- no PR created ---
        prs = list(gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs; got {prs}")

        # Store SHA for idempotency test
        self.__class__._sha_after_first_apply = _get_default_branch_sha(
            self.gh_org, self.repo_name
        )

    # ------------------------------------------------------------------
    # AC4-b: second gw apply is idempotent (same head SHA)
    # ------------------------------------------------------------------

    def test_gw_apply_idempotent_head_sha(self):
        """AC4: second gw apply leaves head SHA unchanged."""
        # Ensure first apply ran (tests run alphabetically)
        first_sha = getattr(self.__class__, "_sha_after_first_apply", None)
        if first_sha is None:
            self.skipTest("First apply did not run; skipping idempotency check")

        result = _run_gw("apply")
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0 on second apply.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        second_sha = _get_default_branch_sha(self.gh_org, self.repo_name)
        self.assertEqual(
            first_sha,
            second_sha,
            f"Second gw apply changed HEAD: {first_sha} → {second_sha}",
        )
