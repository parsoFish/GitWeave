"""
Tests verifying that the gitweave-apply.yaml workflow has been rewired
from the legacy apply-overlays.py script to the gw CLI.

AC1: The dry-run-smoke job (name: 'Apply Configuration') must NOT invoke
     scripts/apply-overlays.py — it must use a gw command instead.
AC2: The apply job's env block must set GW_RESOURCE_PREFIX so gw apply
     scopes its changes by the ownership marker.
"""
from __future__ import annotations

import os
import pathlib
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).parent.parent
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "gitweave-apply.yaml"


def _load_doc() -> dict:
    return yaml.safe_load(WORKFLOW_FILE.read_text()) or {}


def _steps_for_job(doc: dict, job_name_or_id: str) -> list[dict]:
    """Return steps for a job matched by display name or job id."""
    jobs = doc.get("jobs", {})
    # Try matching by display name first.
    for job_id, job in jobs.items():
        if job.get("name") == job_name_or_id or job_id == job_name_or_id:
            return job.get("steps", []) or []
    return []


def _run_blocks_for_job(doc: dict, job_name_or_id: str) -> list[str]:
    return [str(s.get("run", "")) for s in _steps_for_job(doc, job_name_or_id) if s.get("run")]


class TestApplyWorkflowRewired(unittest.TestCase):
    """Verify the workflow is fully rewired to gw commands (no legacy script)."""

    def setUp(self):
        self.assertTrue(
            WORKFLOW_FILE.is_file(),
            f"Workflow file not found: {WORKFLOW_FILE}",
        )
        self.doc = _load_doc()

    # ------------------------------------------------------------------
    # AC1 — dry-run-smoke job must not call apply-overlays.py
    # ------------------------------------------------------------------

    def test_apply_config_no_longer_calls_apply_overlays_py(self):
        """The 'Apply Configuration' job must not invoke scripts/apply-overlays.py."""
        run_blocks = _run_blocks_for_job(self.doc, "Apply Configuration")
        for block in run_blocks:
            self.assertNotIn(
                "apply-overlays.py",
                block,
                "The 'Apply Configuration' (dry-run-smoke) job still calls "
                "scripts/apply-overlays.py — rewire it to a gw command.",
            )

    def test_apply_config_job_uses_gw_command(self):
        """The 'Apply Configuration' job must invoke a gw command."""
        run_blocks = _run_blocks_for_job(self.doc, "Apply Configuration")
        combined = "\n".join(run_blocks)
        self.assertIn(
            "gw ",
            combined,
            "The 'Apply Configuration' job has no gw command — expected 'gw plan' or similar.",
        )

    def test_apply_config_job_uses_fixture_mode(self):
        """The 'Apply Configuration' job must run gw plan --fixture for credential-free CI."""
        run_blocks = _run_blocks_for_job(self.doc, "Apply Configuration")
        combined = "\n".join(run_blocks)
        self.assertIn(
            "gw plan --fixture",
            combined,
            "The 'Apply Configuration' job must run 'gw plan --fixture' for dry-run smoke testing.",
        )

    # ------------------------------------------------------------------
    # AC2 — apply job must set GW_RESOURCE_PREFIX
    # ------------------------------------------------------------------

    def test_apply_job_env_sets_gw_resource_prefix(self):
        """The gw apply (live) job must expose GW_RESOURCE_PREFIX in its env block."""
        doc = self.doc
        jobs = doc.get("jobs", {})
        # Find the apply job — by id or name.
        apply_job = jobs.get("apply") or next(
            (j for j in jobs.values() if "apply" in str(j.get("name", "")).lower()),
            None,
        )
        self.assertIsNotNone(apply_job, "No 'apply' job found in gitweave-apply.yaml.")
        steps = apply_job.get("steps", []) or []
        # Collect all env blocks across the job's steps.
        all_env_keys: set[str] = set()
        for step in steps:
            env = step.get("env") or {}
            all_env_keys.update(env.keys())
        self.assertIn(
            "GW_RESOURCE_PREFIX",
            all_env_keys,
            "The apply job must set GW_RESOURCE_PREFIX in a step env block so "
            "gw apply scopes changes by the ownership marker.",
        )


if __name__ == "__main__":
    unittest.main()
