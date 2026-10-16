"""tests/acceptance/test_gw_containment.py — live acceptance: gw apply+reset containment.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.

Test map (1:1 with ACs):
  1. test_unmarked_resources_unchanged_after_apply_and_reset  — AC1
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from dataclasses import dataclass

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_RESOURCE_PREFIX",
)

def _resource_marker() -> str:
    """Return GW_RESOURCE_PREFIX — the ownership marker gw uses."""
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


@dataclass
class OrgSnapshot:
    """Names of teams, repos, and rulesets in an org at a point in time."""
    teams: frozenset[str]
    repos: frozenset[str]
    rulesets: frozenset[str]


def _snapshot_org(gh_org) -> OrgSnapshot:
    """Read org state through the GitHub API; never parse gw output."""
    teams = frozenset(t.name for t in gh_org.get_teams())
    repos = frozenset(r.name for r in gh_org.get_repos())
    # Rulesets via REST (PyGithub lacks a high-level API for them)
    rulesets: frozenset[str]
    try:
        status, data = gh_org._requester.requestJsonAndCheck(
            "GET",
            f"/orgs/{gh_org.login}/rulesets",
        )
        rulesets = frozenset(rs["name"] for rs in (data or []))
    except Exception:
        rulesets = frozenset()
    return OrgSnapshot(teams=teams, repos=repos, rulesets=rulesets)


def _unmarked(names: frozenset[str], marker: str) -> frozenset[str]:
    """Return names that do NOT carry the resource marker."""
    return frozenset(n for n in names if not n.startswith(marker))


class TestContainment(unittest.TestCase):
    """Live acceptance: gw apply+reset must not touch resources without the marker."""

    def setUp(self):
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            self.fail(
                f"Required env vars not set: {', '.join(missing)}. "
                "Set GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, "
                "GW_ORG, GW_RESOURCE_PREFIX before running acceptance tests."
            )

    def test_unmarked_resources_unchanged_after_apply_and_reset(self):
        """AC1: unmarked teams/repos/rulesets survive gw apply then gw reset."""
        marker = _resource_marker()
        gh_org = _build_gh_org()

        # --- Snapshot before any gw operation (API, not stdout) ---
        before = _snapshot_org(gh_org)
        before_teams = _unmarked(before.teams, marker)
        before_repos = _unmarked(before.repos, marker)
        before_rulesets = _unmarked(before.rulesets, marker)

        # --- Act: apply then reset ---
        apply_result = _run_gw("apply")
        self.assertEqual(
            apply_result.returncode, 0,
            f"gw apply failed.\nstdout={apply_result.stdout}\nstderr={apply_result.stderr}",
        )

        reset_result = _run_gw("reset")
        self.assertEqual(
            reset_result.returncode, 0,
            f"gw reset failed.\nstdout={reset_result.stdout}\nstderr={reset_result.stderr}",
        )

        # --- Snapshot after (API, not stdout) ---
        after = _snapshot_org(gh_org)
        after_teams = _unmarked(after.teams, marker)
        after_repos = _unmarked(after.repos, marker)
        after_rulesets = _unmarked(after.rulesets, marker)

        # --- Assert: every unmarked resource is unchanged ---
        self.assertEqual(
            before_teams,
            after_teams,
            f"Unmarked teams changed.\n"
            f"  disappeared: {before_teams - after_teams}\n"
            f"  appeared:    {after_teams - before_teams}",
        )
        self.assertEqual(
            before_repos,
            after_repos,
            f"Unmarked repos changed.\n"
            f"  disappeared: {before_repos - after_repos}\n"
            f"  appeared:    {after_repos - before_repos}",
        )
        self.assertEqual(
            before_rulesets,
            after_rulesets,
            f"Unmarked rulesets changed.\n"
            f"  disappeared: {before_rulesets - after_rulesets}\n"
            f"  appeared:    {after_rulesets - before_rulesets}",
        )
