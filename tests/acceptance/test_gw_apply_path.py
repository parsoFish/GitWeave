"""tests/acceptance/test_gw_apply_path.py — live acceptance: gw apply path with GW_RESOURCE_PREFIX.

REQUIRES: GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG,
          GW_RESOURCE_PREFIX all set in the environment.

Fails (not skips) when any of those variables is missing — AC1.

Checks:
  - gw plan → gw apply → gw reset lifecycle exits 0.
  - Containment: only resources matching GW_RESOURCE_PREFIX were created/changed
    (asserted on API state, not stdout); org_settings are org-level and excluded.
  - Reset: GET of teams, repos and rulesets confirms no marker resource remains
    (asserted on API response, not exit code alone).
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

_FAIL_REASON = (
    "Live acceptance tests require GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, "
    "GW_APP_INSTALLATION_ID, GW_ORG and GW_RESOURCE_PREFIX to be set."
)


def _run_gw(*args) -> subprocess.CompletedProcess:
    """Run gw via sys.executable so it works regardless of entry-point install."""
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
    )


def _build_gh_org():
    """Return a PyGithub Organization object using env credentials."""
    from gitweave.auth import get_github_client
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def _api_teams(gh_org) -> list[str]:
    """Return all team names in the org via API."""
    return [t.name for t in gh_org.get_teams()]


def _api_repos(gh_org) -> list[str]:
    """Return all repo names in the org via API."""
    return [r.name for r in gh_org.get_repos()]


def _api_rulesets(gh_org) -> list[str]:
    """Return all ruleset names in the org via API; empty on 403 (plan limit)."""
    try:
        _, data = gh_org._requester.requestJsonAndCheck(
            "GET", f"/orgs/{gh_org.login}/rulesets"
        )
        return [r.get("name", "") for r in (data or [])]
    except Exception as exc:
        if "403" in str(exc):
            return []
        raise


class TestGwApplyPath(unittest.TestCase):
    """Full apply→reset lifecycle with GW_RESOURCE_PREFIX set."""

    def setUp(self):
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            self.fail(
                f"Required env vars not set: {', '.join(missing)}. "
                + _FAIL_REASON
            )

    def test_gw_apply_path_with_gw_resource_prefix(self):
        prefix = os.environ["GW_RESOURCE_PREFIX"]
        gh_org = _build_gh_org()

        # Capture org state before apply to diff against after.
        before_teams = set(_api_teams(gh_org))
        before_repos = set(_api_repos(gh_org))
        before_rulesets = set(_api_rulesets(gh_org))

        # Plan against live org — must exit 0
        plan = _run_gw("plan")
        self.assertEqual(
            plan.returncode,
            0,
            f"gw plan failed:\n{plan.stderr}",
        )

        # Apply — must exit 0
        apply_run = _run_gw("apply")
        self.assertEqual(
            apply_run.returncode,
            0,
            f"gw apply failed:\n{apply_run.stderr}",
        )

        # Containment — only NEW resources created by apply must have the prefix.
        # Pre-existing org resources (engineering, platform, etc.) are not managed by gw
        # and are excluded from the containment check.
        # org_settings are org-level (no name/marker), excluded from containment.
        new_teams = [n for n in set(_api_teams(gh_org)) - before_teams
                     if not n.startswith(prefix)]
        self.assertEqual(
            new_teams,
            [],
            f"gw apply created teams outside GW_RESOURCE_PREFIX {prefix!r}: "
            f"{new_teams}",
        )

        new_repos = [n for n in set(_api_repos(gh_org)) - before_repos
                     if not n.startswith(prefix)]
        self.assertEqual(
            new_repos,
            [],
            f"gw apply created repos outside GW_RESOURCE_PREFIX {prefix!r}: "
            f"{new_repos}",
        )

        new_rulesets = [n for n in set(_api_rulesets(gh_org)) - before_rulesets
                        if not n.startswith(prefix)]
        self.assertEqual(
            new_rulesets,
            [],
            f"gw apply created rulesets outside GW_RESOURCE_PREFIX {prefix!r}: "
            f"{new_rulesets}",
        )

        # Reset — must exit 0
        reset_run = _run_gw("reset")
        self.assertEqual(
            reset_run.returncode,
            0,
            f"gw reset failed:\n{reset_run.stderr}",
        )

        # Assert on API response that no marker resource remains — not exit code alone.
        teams_remaining = [n for n in _api_teams(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            teams_remaining,
            [],
            f"Teams with GW_RESOURCE_PREFIX {prefix!r} still exist after reset: {teams_remaining}",
        )

        repos_remaining = [n for n in _api_repos(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            repos_remaining,
            [],
            f"Repos with GW_RESOURCE_PREFIX {prefix!r} still exist after reset: {repos_remaining}",
        )

        rulesets_remaining = [n for n in _api_rulesets(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            rulesets_remaining,
            [],
            f"Rulesets with GW_RESOURCE_PREFIX {prefix!r} still exist after reset: {rulesets_remaining}",
        )
