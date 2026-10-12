"""tests/acceptance/test_gw_apply_path.py — live acceptance: gw apply path with GW_RESOURCE_PREFIX.

REQUIRES: GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG,
          GW_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.

Checks:
  - gw plan → gw apply → gw reset lifecycle exits 0.
  - Containment: only resources matching GW_RESOURCE_PREFIX were created/changed
    (asserted on API state, not stdout); org_settings are org-level and excluded.
  - Reset: GET of teams, repos and rulesets confirms no marker resource remains
    (asserted on API response, not exit code alone).
  - With FORGE_RESOURCE_PREFIX set, scope narrows to that prefix only.
"""

from __future__ import annotations

import os
import subprocess
import unittest

_BASE_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_RESOURCE_PREFIX",
)

_FORGE_REQUIRED_VARS = _BASE_REQUIRED_VARS + ("FORGE_RESOURCE_PREFIX",)

_SKIP_BASE_REASON = (
    "Live acceptance tests require GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, "
    "GW_APP_INSTALLATION_ID, GW_ORG and GW_RESOURCE_PREFIX to be set."
)

_SKIP_FORGE_REASON = (
    "Forge-prefix narrowing test additionally requires FORGE_RESOURCE_PREFIX to be set."
)


def _have_base_credentials() -> bool:
    return all(os.environ.get(v) for v in _BASE_REQUIRED_VARS)


def _have_forge_credentials() -> bool:
    return all(os.environ.get(v) for v in _FORGE_REQUIRED_VARS)


def _run_gw(*args) -> subprocess.CompletedProcess:
    """Run gw with current environment (credentials must be set)."""
    return subprocess.run(
        ["gw", *args],
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


@unittest.skipUnless(_have_base_credentials(), _SKIP_BASE_REASON)
class TestGwApplyPath(unittest.TestCase):
    """Full apply→reset lifecycle with GW_RESOURCE_PREFIX set."""

    def test_gw_apply_path_with_gw_resource_prefix(self):
        prefix = os.environ["GW_RESOURCE_PREFIX"]
        gh_org = _build_gh_org()

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

        # AC3: Containment — assert on API state, not stdout.
        # org_settings are org-level (no name/marker), excluded from containment.
        all_teams = _api_teams(gh_org)
        non_prefixed_teams = [n for n in all_teams if not n.startswith(prefix)]
        self.assertEqual(
            non_prefixed_teams,
            [],
            f"gw apply created/modified teams outside GW_RESOURCE_PREFIX={prefix!r}: "
            f"{non_prefixed_teams}",
        )

        all_repos = _api_repos(gh_org)
        non_prefixed_repos = [n for n in all_repos if not n.startswith(prefix)]
        self.assertEqual(
            non_prefixed_repos,
            [],
            f"gw apply created/modified repos outside GW_RESOURCE_PREFIX={prefix!r}: "
            f"{non_prefixed_repos}",
        )

        all_rulesets = _api_rulesets(gh_org)
        non_prefixed_rulesets = [n for n in all_rulesets if not n.startswith(prefix)]
        self.assertEqual(
            non_prefixed_rulesets,
            [],
            f"gw apply created/modified rulesets outside GW_RESOURCE_PREFIX={prefix!r}: "
            f"{non_prefixed_rulesets}",
        )

        # Reset — must exit 0
        reset_run = _run_gw("reset")
        self.assertEqual(
            reset_run.returncode,
            0,
            f"gw reset failed:\n{reset_run.stderr}",
        )

        # AC2: Assert on API response that no marker resource remains — not exit code alone.
        teams_remaining = [n for n in _api_teams(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            teams_remaining,
            [],
            f"Teams with marker prefix {prefix!r} still exist after reset: {teams_remaining}",
        )

        repos_remaining = [n for n in _api_repos(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            repos_remaining,
            [],
            f"Repos with marker prefix {prefix!r} still exist after reset: {repos_remaining}",
        )

        rulesets_remaining = [n for n in _api_rulesets(gh_org) if n.startswith(prefix)]
        self.assertEqual(
            rulesets_remaining,
            [],
            f"Rulesets with marker prefix {prefix!r} still exist after reset: {rulesets_remaining}",
        )


@unittest.skipUnless(_have_forge_credentials(), _SKIP_FORGE_REASON)
class TestForgeResourcePrefixNarrowing(unittest.TestCase):
    """With FORGE_RESOURCE_PREFIX set, apply scope narrows to that prefix."""

    def test_forge_prefix_narrowing_live(self):
        forge_prefix = os.environ["FORGE_RESOURCE_PREFIX"]
        gh_org = _build_gh_org()

        # Plan — must exit 0
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
            f"gw apply failed (forge narrowing):\n{apply_run.stderr}",
        )

        # Containment: no team/repo/ruleset outside FORGE_RESOURCE_PREFIX (API state).
        # org_settings are org-level, excluded.
        all_teams = _api_teams(gh_org)
        non_forge_teams = [n for n in all_teams if not n.startswith(forge_prefix)]
        self.assertEqual(
            non_forge_teams,
            [],
            f"Teams outside FORGE_RESOURCE_PREFIX={forge_prefix!r} after apply: "
            f"{non_forge_teams}",
        )

        all_repos = _api_repos(gh_org)
        non_forge_repos = [n for n in all_repos if not n.startswith(forge_prefix)]
        self.assertEqual(
            non_forge_repos,
            [],
            f"Repos outside FORGE_RESOURCE_PREFIX={forge_prefix!r} after apply: "
            f"{non_forge_repos}",
        )

        # Reset — clean up
        reset_run = _run_gw("reset")
        self.assertEqual(
            reset_run.returncode,
            0,
            f"gw reset failed (forge narrowing cleanup):\n{reset_run.stderr}",
        )
