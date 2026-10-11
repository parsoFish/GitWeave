"""tests/acceptance/test_gw_reset_before_apply.py — live acceptance: gw reset idempotency.

REQUIRES: GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG,
          FORGE_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.

Checks:
  - gw reset twice → second run reports nothing changed.
  - After gw reset, no FORGE_RESOURCE_PREFIX resource remains.
"""

import json
import os
import subprocess
import unittest

_REQUIRED_VARS = (
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
    "FORGE_RESOURCE_PREFIX",
)

_SKIP_REASON = (
    "Live acceptance tests require GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, "
    "GW_APP_INSTALLATION_ID, GW_ORG and FORGE_RESOURCE_PREFIX to be set."
)


def _have_credentials() -> bool:
    return all(os.environ.get(v) for v in _REQUIRED_VARS)


def _run_gw(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gw", *args],
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(_have_credentials(), _SKIP_REASON)
class TestResetIdempotency(unittest.TestCase):
    """gw reset twice → second run changes nothing."""

    def test_reset_twice_second_run_changes_nothing(self):
        # First reset — may or may not change anything
        r1 = _run_gw("reset")
        self.assertEqual(r1.returncode, 0, f"First reset failed:\n{r1.stderr}")

        # Second reset — must be a no-op
        r2 = _run_gw("reset")
        self.assertEqual(r2.returncode, 0, f"Second reset failed:\n{r2.stderr}")
        self.assertIn(
            "Nothing changed",
            r2.stdout,
            f"Second gw reset should print 'Nothing changed.' but got:\n{r2.stdout!r}",
        )

    def test_no_prefixed_resources_after_reset(self):
        prefix = os.environ["FORGE_RESOURCE_PREFIX"]

        # Ensure clean state
        r = _run_gw("reset")
        self.assertEqual(r.returncode, 0, f"reset failed:\n{r.stderr}")

        # No prefixed teams
        rt = _run_gw("org", "teams", "--json")
        self.assertEqual(rt.returncode, 0, rt.stderr)
        teams = json.loads(rt.stdout)
        prefixed_teams = [t["name"] for t in teams if t["name"].startswith(prefix)]
        self.assertEqual(
            prefixed_teams,
            [],
            f"Prefixed teams still present after reset: {prefixed_teams}",
        )

        # No prefixed repos
        rr = _run_gw("org", "repos", "--json")
        self.assertEqual(rr.returncode, 0, rr.stderr)
        repos = json.loads(rr.stdout)
        prefixed_repos = [r["name"] for r in repos if r["name"].startswith(prefix)]
        self.assertEqual(
            prefixed_repos,
            [],
            f"Prefixed repos still present after reset: {prefixed_repos}",
        )

        # No prefixed rulesets
        rul = _run_gw("org", "rulesets", "--json")
        self.assertEqual(rul.returncode, 0, rul.stderr)
        rulesets = json.loads(rul.stdout)
        prefixed_rulesets = [rs["name"] for rs in rulesets if rs["name"].startswith(prefix)]
        self.assertEqual(
            prefixed_rulesets,
            [],
            f"Prefixed rulesets still present after reset: {prefixed_rulesets}",
        )


if __name__ == "__main__":
    unittest.main()
