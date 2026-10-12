"""tests/acceptance/test_gw_apply_path.py — live acceptance: gw apply path with GW_RESOURCE_PREFIX.

REQUIRES: GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG,
          GW_RESOURCE_PREFIX all set in the environment.

Skips when any of those variables is missing.

Checks:
  - gw plan → gw apply → gw reset lifecycle exits 0.
  - Only resources matching GW_RESOURCE_PREFIX are touched.
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


@unittest.skipUnless(_have_base_credentials(), _SKIP_BASE_REASON)
class TestGwApplyPath(unittest.TestCase):
    """Full apply→reset lifecycle with GW_RESOURCE_PREFIX set."""

    def test_gw_apply_path_with_gw_resource_prefix(self):
        prefix = os.environ["GW_RESOURCE_PREFIX"]

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

        # Verify apply output does not mention resources outside GW_RESOURCE_PREFIX.
        # Any resource name printed by apply that starts with a different prefix is a
        # scope violation.  We check stdout lines that name a resource — a line is
        # suspicious only if it contains a word that looks like a resource slug and
        # does NOT start with our prefix.  We use a simple heuristic: ignore blank
        # lines, header lines and lines without a colon; the rest should only
        # reference prefixed names.
        for line in apply_run.stdout.splitlines():
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue
            # Extract the value part (after the colon)
            _, _, value = stripped.partition(":")
            resource_name = value.strip().split()[0] if value.strip() else ""
            if resource_name and not resource_name.startswith(prefix):
                # Allow generic action words and status tokens
                skip_tokens = {
                    "create", "update", "delete", "unchanged", "ok", "done",
                    "error", "warning", "info", "0", "true", "false",
                }
                if resource_name.lower() not in skip_tokens:
                    self.fail(
                        f"gw apply output mentions resource '{resource_name}' "
                        f"which does not start with GW_RESOURCE_PREFIX={prefix!r}.\n"
                        f"Full line: {stripped!r}"
                    )

        # Reset — must exit 0
        reset_run = _run_gw("reset")
        self.assertEqual(
            reset_run.returncode,
            0,
            f"gw reset failed:\n{reset_run.stderr}",
        )


@unittest.skipUnless(_have_forge_credentials(), _SKIP_FORGE_REASON)
class TestForgeResourcePrefixNarrowing(unittest.TestCase):
    """With FORGE_RESOURCE_PREFIX set, apply scope narrows to that prefix."""

    def test_forge_prefix_narrowing_live(self):
        forge_prefix = os.environ["FORGE_RESOURCE_PREFIX"]

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

        # No resource outside FORGE_RESOURCE_PREFIX should appear in apply output.
        for line in apply_run.stdout.splitlines():
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue
            _, _, value = stripped.partition(":")
            resource_name = value.strip().split()[0] if value.strip() else ""
            if resource_name and not resource_name.startswith(forge_prefix):
                skip_tokens = {
                    "create", "update", "delete", "unchanged", "ok", "done",
                    "error", "warning", "info", "0", "true", "false",
                }
                if resource_name.lower() not in skip_tokens:
                    self.fail(
                        f"gw apply mutated resource '{resource_name}' "
                        f"outside FORGE_RESOURCE_PREFIX={forge_prefix!r}.\n"
                        f"Full line: {stripped!r}"
                    )

        # Reset — clean up
        reset_run = _run_gw("reset")
        self.assertEqual(
            reset_run.returncode,
            0,
            f"gw reset failed (forge narrowing cleanup):\n{reset_run.stderr}",
        )
