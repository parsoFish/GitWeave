"""tests/acceptance/test_gw_reset_readback.py — live acceptance: gw reset idempotency.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.

Test map (1:1 with ACs):
  1. test_reset_removes_prefixed_resources_and_is_idempotent  — AC1
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_RESOURCE_PREFIX",
)

def _effective_prefix() -> str:
    """Return GW_RESOURCE_PREFIX — the ownership marker for all gw-created resources."""
    return os.environ["GW_RESOURCE_PREFIX"]


def _run_gw(*args) -> subprocess.CompletedProcess:
    """Run gw via sys.executable so it works regardless of entry-point install."""
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
    )


def _build_gh_org():
    """Return a PyGithub Organization object via App credentials."""
    from gitweave.auth import get_github_client
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def _team_exists(gh_org, team_name: str) -> bool:
    try:
        gh_org.get_team_by_slug(team_name)
        return True
    except Exception:
        return False


def _repo_exists(gh_org, repo_name: str) -> bool:
    try:
        gh_org.get_repo(repo_name)
        return True
    except Exception:
        return False


def _delete_team_if_exists(gh_org, team_name: str) -> None:
    try:
        gh_org.get_team_by_slug(team_name).delete()
    except Exception:
        pass


def _delete_repo_if_exists(gh_org, repo_name: str) -> None:
    try:
        gh_org.get_repo(repo_name).delete()
    except Exception:
        pass


class TestResetReadback(unittest.TestCase):
    """Live acceptance: gw reset deletes prefixed resources; idempotent on clean state."""

    def setUp(self):
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            self.skipTest(
                f"Required env vars not set: {', '.join(missing)}. "
                "Set GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, "
                "GW_ORG, GW_RESOURCE_PREFIX before running acceptance tests."
            )

    def test_reset_removes_prefixed_resources_and_is_idempotent(self):
        """AC1: create prefixed team + repo, reset twice, verify via API."""
        prefix = _effective_prefix()
        team_name = f"{prefix}reset-acc-team"
        repo_name = f"{prefix}reset-acc-repo"
        gh_org = _build_gh_org()

        # --- Arrange: create one prefixed team and one prefixed repo via API ---
        _delete_team_if_exists(gh_org, team_name)
        _delete_repo_if_exists(gh_org, repo_name)
        gh_org.create_team(team_name, privacy="closed")
        gh_org.create_repo(repo_name, private=True, auto_init=False)

        try:
            self.assertTrue(
                _team_exists(gh_org, team_name),
                f"Setup failed: team {team_name!r} not created",
            )
            self.assertTrue(
                _repo_exists(gh_org, repo_name),
                f"Setup failed: repo {repo_name!r} not created",
            )

            # --- Act: first reset ---
            first = _run_gw("reset")
            self.assertEqual(
                first.returncode, 0,
                f"First reset expected exit 0.\nstdout={first.stdout}\nstderr={first.stderr}",
            )

            # --- Assert: resources gone (API read-back, not gw output) ---
            self.assertFalse(
                _team_exists(gh_org, team_name),
                f"Team {team_name!r} still exists after first reset",
            )
            self.assertFalse(
                _repo_exists(gh_org, repo_name),
                f"Repo {repo_name!r} still exists after first reset",
            )

            # --- Act: second reset (idempotent) ---
            second = _run_gw("reset")
            self.assertEqual(
                second.returncode, 0,
                f"Second reset expected exit 0.\nstdout={second.stdout}\nstderr={second.stderr}",
            )
            self.assertIn(
                "Nothing changed.",
                second.stdout,
                f"Expected 'Nothing changed.' on second reset.\nstdout={second.stdout}",
            )

        finally:
            # Safety clean-up in case the first reset failed partway
            _delete_team_if_exists(gh_org, team_name)
            _delete_repo_if_exists(gh_org, repo_name)
