"""tests/acceptance/test_gw_workflow.py — live acceptance: gw apply idempotency.

REQUIRES: GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG,
          GW_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.
"""

import json
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

_VOLATILE_KEYS = frozenset({
    "id", "node_id", "created_at", "updated_at",
    "source", "source_type", "url", "html_url",
    "links", "_links",
})


def _strip_volatile(obj):
    """Recursively remove volatile keys from dicts/lists for stable comparison."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return sorted(
            [_strip_volatile(i) for i in obj],
            key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x),
        )
    return obj


def _run_gw(*args) -> subprocess.CompletedProcess:
    """Run gw via sys.executable so it works regardless of entry-point install."""
    return subprocess.run(
        [sys.executable, "-m", "gitweave.cli", *args],
        capture_output=True,
        text=True,
    )


class TestApplyIdempotency(unittest.TestCase):
    """gw apply --json twice yields identical stable state."""

    def setUp(self):
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            self.fail(
                f"Required env vars not set: {', '.join(missing)}. "
                "Set GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, "
                "GW_ORG, GW_RESOURCE_PREFIX before running acceptance tests."
            )

    def test_apply_json_twice_identical_state(self):
        # First apply
        r1 = _run_gw("apply", "--json")
        self.assertEqual(r1.returncode, 0, f"First apply failed:\n{r1.stderr}")
        data1 = json.loads(r1.stdout)
        self.assertIn("state", data1, "JSON missing 'state' key")

        # Second apply
        r2 = _run_gw("apply", "--json")
        self.assertEqual(r2.returncode, 0, f"Second apply failed:\n{r2.stderr}")
        data2 = json.loads(r2.stdout)
        self.assertIn("state", data2, "JSON missing 'state' key")

        state1 = _strip_volatile(data1["state"])
        state2 = _strip_volatile(data2["state"])
        self.assertEqual(
            state1,
            state2,
            "State diverged between two consecutive apply --json runs "
            f"(volatile keys stripped).\nFirst:  {json.dumps(state1, indent=2)}\n"
            f"Second: {json.dumps(state2, indent=2)}",
        )

    def test_apply_json_statuses_have_no_errors(self):
        r = _run_gw("apply", "--json")
        self.assertEqual(r.returncode, 0, f"apply --json failed:\n{r.stderr}")
        data = json.loads(r.stdout)
        errors = [s for s in data.get("statuses", []) if s.get("status") == "error"]
        self.assertEqual(errors, [], f"apply --json reported errors: {errors}")


class TestExtraTeamAbsentAfterApply(unittest.TestCase):
    """A prefixed team NOT in the declaration is absent after gw apply --json."""

    def setUp(self):
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            self.fail(
                f"Required env vars not set: {', '.join(missing)}. "
                "Set GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, "
                "GW_ORG, GW_RESOURCE_PREFIX before running acceptance tests."
            )

        from gitweave.auth import get_github_client

        self._gh = get_github_client()
        self._gh_org = self._gh.get_organization(os.environ["GW_ORG"])
        self._prefix = os.environ["GW_RESOURCE_PREFIX"]
        self._extra_team = f"{self._prefix}extra-stale-team"

    def test_stale_prefixed_team_removed_by_apply(self):
        # Ensure the extra team exists before the apply
        try:
            self._gh_org.create_team(
                self._extra_team,
                description="stale team for acceptance test",
                privacy="closed",
            )
        except Exception as exc:
            # Already exists → fine; any other error → fail
            if "already_exists" not in str(exc).lower() and "422" not in str(exc):
                raise

        # Verify it appears in gw org teams
        r_before = _run_gw("org", "teams", "--json")
        self.assertEqual(r_before.returncode, 0, r_before.stderr)
        teams_before = {t["name"] for t in json.loads(r_before.stdout)}
        self.assertIn(
            self._extra_team,
            teams_before,
            f"Extra team {self._extra_team!r} not found before apply — "
            "possibly a prefix mismatch.",
        )

        # apply --json → reset-before-apply deletes the extra team
        r_apply = _run_gw("apply", "--json")
        self.assertEqual(r_apply.returncode, 0, f"apply --json failed:\n{r_apply.stderr}")

        # Verify extra team is gone
        r_after = _run_gw("org", "teams", "--json")
        self.assertEqual(r_after.returncode, 0, r_after.stderr)
        teams_after = {t["name"] for t in json.loads(r_after.stdout)}
        self.assertNotIn(
            self._extra_team,
            teams_after,
            f"Extra team {self._extra_team!r} still present after gw apply --json.",
        )


if __name__ == "__main__":
    unittest.main()
