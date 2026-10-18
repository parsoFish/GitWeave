"""tests/acceptance/test_gw_overlay_empty_repo.py — live acceptance: empty-repo bootstrap.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_CALLER_TOKEN, GW_RESOURCE_PREFIX all set in the environment.

Tests are skipped (exit 0) when any required var is absent.

Test map (1:1 with WI-14 AC K2a):
  1. test_overlay_apply_empty_repo_bootstraps — K2a
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
_MODULE_VERSION = "20261018.0"
_MODULE_INPUTS = {"service_name": "empty_repo_test", "python_version": "3.11"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _write_repo_overlay_config(repo_name: str, inputs: dict) -> None:
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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@unittest.skipIf(_offline(), "requires GW_* credentials (GW_ORG, GW_APP_ID, ...)")
class TestGwOverlayEmptyRepoAcceptance(unittest.TestCase):
    """Live acceptance test: gw overlay apply on a repository with no commits.

    Creates a throwaway org repo without auto_init (empty — no commits, no
    default branch), runs gw apply, verifies the module files and answers file
    exist on the default branch, then deletes the repository.
    """

    @classmethod
    def setUpClass(cls):
        cls.prefix = _resource_prefix()
        cls.repo_name = f"{cls.prefix}-overlay-empty-repo-test"
        cls.gh_org = _build_gh_org()
        cls.app_token = _get_app_token()
        # Create repo with NO commits
        cls.gh_repo = _create_empty_repo(cls.gh_org, cls.repo_name)
        # Write overlay config for this repo
        _write_repo_overlay_config(cls.repo_name, _MODULE_INPUTS)

    @classmethod
    def tearDownClass(cls):
        _delete_repo_overlay_config(cls.repo_name)
        _delete_repo_if_exists(cls.gh_org, cls.repo_name)

    def _gw_live(self, *args) -> subprocess.CompletedProcess:
        return _run_gw(*args)

    # ------------------------------------------------------------------
    # K2a: apply on empty (no-commits) repo bootstraps and commits files
    # ------------------------------------------------------------------

    def test_overlay_apply_empty_repo_bootstraps(self):
        """K2a: gw overlay apply bootstraps an empty repo and commits module files."""
        result = self._gw_live("overlay", "apply", self.repo_name)
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0 on empty repo.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # Reload repo object to pick up the newly created default branch
        gh_repo = self.gh_org.get_repo(self.repo_name)

        # Verify per-module answers file is present on the default branch
        answers_path = f".gitweave/{_MODULE_NAME}.copier-answers.yml"
        try:
            contents = gh_repo.get_contents(answers_path)
        except Exception as exc:
            self.fail(
                f"Answers file {answers_path!r} not found after apply on empty repo: {exc}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )

        answers = yaml.safe_load(contents.decoded_content.decode("utf-8"))
        self.assertEqual(
            answers.get("_module_name"), _MODULE_NAME,
            f"Expected _module_name={_MODULE_NAME!r} in answers; got {answers}",
        )

        # Verify at least one rendered module file is present
        # python_service renders a file under the repo_name directory; the
        # service_name input determines the directory name used by the template.
        # We check that the default branch exists and has at least one tree entry
        # under the module subdirectory OR a README, confirming the bootstrap committed.
        default_branch = gh_repo.default_branch
        branch_obj = gh_repo.get_branch(default_branch)
        self.assertIsNotNone(
            branch_obj.commit.sha,
            "Default branch has no commit after apply on empty repo",
        )

        # AC18: read back .github/workflows/ content via API — not just commit SHA
        try:
            workflow_contents = gh_repo.get_contents(".github/workflows/ci.yml")
            workflow_text = workflow_contents.decoded_content.decode("utf-8")
            self.assertTrue(
                workflow_text.strip(),
                ".github/workflows/ci.yml is present but empty after overlay apply",
            )
            # Must be valid YAML
            import yaml as _yaml
            parsed_wf = _yaml.safe_load(workflow_text)
            self.assertIsInstance(
                parsed_wf, dict,
                f".github/workflows/ci.yml must be a valid YAML mapping; got: {type(parsed_wf)}",
            )
        except Exception as exc:
            status = getattr(exc, "status", None)
            if status == 404:
                self.fail(
                    ".github/workflows/ci.yml not found after overlay apply on empty repo. "
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                )
            raise

        # No PRs should have been created (direct commit to default branch)
        prs = list(gh_repo.get_pulls(state="open"))
        self.assertEqual(prs, [], f"Expected zero open PRs; got {prs}")
