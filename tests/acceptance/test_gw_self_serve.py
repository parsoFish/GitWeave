"""tests/acceptance/test_gw_self_serve.py — live acceptance: gw self-serve commands.

REQUIRES: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH,
          GW_CALLER_TOKEN all set in the environment.

Skips when any of those variables is missing.

Test map (1:1 with ACs):
  1. test_new_repo_within_policy          — AC1
  2. test_update_content_topics           — AC2
  3. test_add_member_within_policy        — AC3
  4. test_policy_exception_roundtrip      — AC4
  5. test_policy_violation_refused        — AC5
  6. test_missing_caller_token            — AC6
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "GW_CALLER_TOKEN",
)

_SKIP_REASON = (
    "Live acceptance tests require GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, "
    "GW_APP_INSTALLATION_ID, GW_ORG and GW_CALLER_TOKEN to be set."
)


def _have_credentials() -> bool:
    return all(os.environ.get(v) for v in _REQUIRED_VARS)


def _resource_prefix() -> str:
    """Return FORGE_RESOURCE_PREFIX or a safe default for acceptance runs."""
    return os.environ.get("FORGE_RESOURCE_PREFIX", "gw-acc-")


def _run_gw(*args) -> subprocess.CompletedProcess:
    """Run gw with current environment (credentials must be set)."""
    return subprocess.run(["gw", *args], capture_output=True, text=True)


def _build_gh_org():
    """Return a PyGithub Organization object via App credentials."""
    from gitweave.auth import get_github_client
    gh = get_github_client()
    return gh.get_organization(os.environ["GW_ORG"])


def _caller_login() -> str:
    """Resolve the GitHub login of the GW_CALLER_TOKEN holder."""
    from gitweave.auth import get_caller_token, resolve_caller_login
    return resolve_caller_login(get_caller_token())


def _delete_repo_if_exists(gh_org, repo_name: str) -> None:
    """Delete *repo_name* in *gh_org*; silently ignore if it doesn't exist."""
    try:
        gh_org.get_repo(repo_name).delete()
    except Exception:
        pass


@unittest.skipUnless(_have_credentials(), _SKIP_REASON)
class TestSelfServeAcceptance(unittest.TestCase):
    """Live acceptance tests for gw self-serve subcommands."""

    # ------------------------------------------------------------------
    # AC1: new-repo within policy
    # ------------------------------------------------------------------
    def test_new_repo_within_policy(self):
        prefix = _resource_prefix()
        repo_name = f"forge-{prefix}ss-new-repo"
        gh_org = _build_gh_org()
        _delete_repo_if_exists(gh_org, repo_name)  # ensure clean state

        try:
            result = _run_gw(
                "self-serve", "new-repo",
                "--team", "platform",
                "--name", repo_name,
            )
            self.assertEqual(
                result.returncode, 0,
                f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
            )

            # Verify repo exists via GitHub API (not just command output)
            repo = gh_org.get_repo(repo_name)
            self.assertEqual(repo.name, repo_name)
        finally:
            _delete_repo_if_exists(gh_org, repo_name)

    # ------------------------------------------------------------------
    # AC2: update-content (topics)
    # ------------------------------------------------------------------
    def test_update_content_topics(self):
        prefix = _resource_prefix()
        repo_name = f"forge-{prefix}ss-topics-repo"
        gh_org = _build_gh_org()

        # Create repo to work with; ignore if already exists
        try:
            gh_org.create_repo(repo_name, private=False)
        except Exception:
            pass

        try:
            result = _run_gw(
                "self-serve", "update-content",
                "--team", "platform",
                "--repo", repo_name,
                "--setting", "topics",
                "--value", "forge,test",
            )
            self.assertEqual(
                result.returncode, 0,
                f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
            )

            # Verify topics applied via API read-back
            repo = gh_org.get_repo(repo_name)
            topics = repo.get_topics()
            self.assertIn("forge", topics)
            self.assertIn("test", topics)
        finally:
            _delete_repo_if_exists(gh_org, repo_name)

    # ------------------------------------------------------------------
    # AC3: add-member within policy
    # ------------------------------------------------------------------
    def test_add_member_within_policy(self):
        login = _caller_login()
        gh_org = _build_gh_org()

        # Ensure caller is in platform team via App token (prerequisite)
        from gitweave.auth import get_github_client
        gh = get_github_client()
        gh_user = gh.get_user(login)
        gh_team = gh_org.get_team_by_slug("platform")
        gh_team.add_membership(gh_user)

        result = _run_gw(
            "self-serve", "add-member",
            "--team", "platform",
            "--member", login,
        )
        self.assertEqual(
            result.returncode, 0,
            f"Expected exit 0.\nstdout={result.stdout}\nstderr={result.stderr}",
        )

        # Verify membership via API
        membership = gh_team.get_team_membership(login)
        self.assertEqual(membership.state, "active")

    # ------------------------------------------------------------------
    # AC4: policy exception roundtrip
    # ------------------------------------------------------------------
    def test_policy_exception_roundtrip(self):
        prefix = _resource_prefix()
        repo_name = f"forge-{prefix}ss-exc-repo"
        gh_org = _build_gh_org()

        # Create repo for exception test; ignore if already exists
        try:
            gh_org.create_repo(repo_name, private=False)
        except Exception:
            pass

        try:
            # Add exception via self-serve
            add_result = _run_gw(
                "self-serve", "add-exception",
                "--team", "platform",
                "--repo", repo_name,
                "--exception", "skip-codeowners",
                "--reason", "acceptance test",
            )
            self.assertEqual(
                add_result.returncode, 0,
                f"Expected exit 0.\nstdout={add_result.stdout}\nstderr={add_result.stderr}",
            )

            # List exceptions — must include the one we just added
            list_result = _run_gw("self-serve", "list-exceptions", "--repo", repo_name)
            self.assertEqual(
                list_result.returncode, 0,
                f"Expected exit 0.\nstdout={list_result.stdout}\nstderr={list_result.stderr}",
            )
            self.assertIn("skip-codeowners", list_result.stdout)

            # Verify via direct API read-back (GET /repos/{org}/{repo}/properties/values)
            org_login = gh_org.login
            _, props = gh_org._requester.requestJsonAndCheck(
                "GET", f"/repos/{org_login}/{repo_name}/properties/values"
            )
            prop_values = [p.get("value") for p in (props or [])
                           if "gw-policy-exception" in p.get("property_name", "")]
            self.assertIn("skip-codeowners", prop_values)
        finally:
            _delete_repo_if_exists(gh_org, repo_name)

    # ------------------------------------------------------------------
    # AC5: policy violation refused
    # ------------------------------------------------------------------
    def test_policy_violation_refused(self):
        # Repo name doesn't match platform team's allowed_repo_patterns (forge-*)
        result = _run_gw(
            "self-serve", "new-repo",
            "--team", "platform",
            "--name", "notallowed-violation-test-repo",
        )
        self.assertNotEqual(
            result.returncode, 0,
            "Expected non-zero exit for policy violation.",
        )
        combined = result.stdout + result.stderr
        # Output must name the specific policy rule
        self.assertTrue(
            any(keyword in combined.lower()
                for keyword in ("pattern", "policy", "allowed_repo_patterns")),
            f"Expected policy rule name in output. Got:\n{combined}",
        )

    # ------------------------------------------------------------------
    # AC6: missing caller token
    # ------------------------------------------------------------------
    def test_missing_caller_token(self):
        # Build env without GW_CALLER_TOKEN, GH_TOKEN, GITHUB_TOKEN
        # Use a fake HOME so `gh auth token` also fails (no stored credentials)
        env = {
            k: v for k, v in os.environ.items()
            if k not in ("GW_CALLER_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
        }
        # Preserve PYTHONUSERBASE so the `gw` entry-point can still import
        # gitweave after HOME is overridden (Python resolves user site-packages
        # via HOME when PYTHONUSERBASE is not set).
        env["PYTHONUSERBASE"] = os.path.join(os.path.expanduser("~"), ".local")
        with tempfile.TemporaryDirectory() as fake_home:
            env["HOME"] = fake_home
            result = subprocess.run(
                ["gw", "self-serve", "new-repo", "--team", "platform", "--name", "any-repo"],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(
            result.returncode, 0,
            "Expected non-zero exit when no caller token is available.",
        )
        combined = result.stdout + result.stderr
        self.assertIn(
            "caller-token-required", combined,
            f"Expected 'caller-token-required' in output. Got:\n{combined}",
        )
