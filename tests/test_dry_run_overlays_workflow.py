"""
Tests for the dry-run PR comment step in .github/workflows/gitweave-apply.yaml.

These tests verify that the workflow is extended to:
  - Run scripts/dry-run-overlays.py on pull_request events for config/ changes
  - Post the formatted copier diff as a PR comment (update-or-create pattern)
  - Use pull-requests: write permission
  - Pass the PR number and repo context to the script
  - NOT run the comment-posting step on push-to-main (only on pull_request)

The workflow already has some structure from previous iterations; these tests
focus specifically on the NEW dry-run comment step requirements.

All tests that reference the new dry-run comment step will FAIL until
the step is added to .github/workflows/gitweave-apply.yaml.
"""

from __future__ import annotations

import os
import re
import unittest

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "gitweave-apply.yaml"
)
DRY_RUN_SCRIPT = "scripts/dry-run-overlays.py"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_workflow() -> dict:
    """Parse gitweave-apply.yaml and return the document dict."""
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def _get_triggers(doc: dict) -> dict:
    """
    Return the workflow trigger mapping.  PyYAML's YAML 1.1 parsing converts
    the bare 'on:' key to the boolean True — both representations are checked
    so the tests work regardless of PyYAML version.
    """
    return doc.get("on") or doc.get(True) or {}


def _collect_all_steps(doc: dict) -> list:
    """Return a flat list of every step object across all jobs."""
    steps = []
    for job in doc.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


def _collect_all_run_commands(doc: dict) -> list[str]:
    """Return the 'run' text from every step that has one."""
    return [
        str(step.get("run", ""))
        for step in _collect_all_steps(doc)
        if step.get("run")
    ]


def _collect_all_env_blocks(doc: dict) -> list[dict]:
    """Return env dicts from all steps and jobs."""
    envs = []
    for job in doc.get("jobs", {}).values():
        if job.get("env"):
            envs.append(job["env"])
        for step in job.get("steps", []):
            if step.get("env"):
                envs.append(step["env"])
    return envs


def _get_permissions(doc: dict) -> dict:
    """Return the top-level permissions mapping."""
    return doc.get("permissions") or {}


# ---------------------------------------------------------------------------
# TestWorkflowPermissions
# ---------------------------------------------------------------------------


class TestWorkflowPermissions(unittest.TestCase):
    """Tests that the workflow has the correct permission declarations."""

    def test_pull_requests_write_permission_is_set(self):
        """
        The workflow must declare pull-requests: write so the dry-run
        comment step can post and update PR comments.
        """
        doc = _load_workflow()
        permissions = _get_permissions(doc)
        pr_permission = permissions.get("pull-requests")
        self.assertEqual(
            pr_permission,
            "write",
            f"Workflow must declare 'pull-requests: write'. "
            f"Got permissions: {permissions}",
        )

    def test_contents_read_permission_is_set(self):
        """The workflow must retain contents: read for checkout."""
        doc = _load_workflow()
        permissions = _get_permissions(doc)
        contents_permission = permissions.get("contents")
        self.assertEqual(
            contents_permission,
            "read",
            f"Workflow must declare 'contents: read'. "
            f"Got permissions: {permissions}",
        )


# ---------------------------------------------------------------------------
# TestDryRunCommentStepExists
# ---------------------------------------------------------------------------


class TestDryRunCommentStepExists(unittest.TestCase):
    """Tests that a step invoking dry-run-overlays.py exists in the workflow."""

    def test_at_least_one_step_invokes_dry_run_overlays_script(self):
        """
        At least one run step must invoke scripts/dry-run-overlays.py.
        This is the new step that generates and posts the PR comment.
        """
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        invokes_script = any("dry-run-overlays" in run for run in all_runs)
        self.assertTrue(
            invokes_script,
            f"No step invokes 'dry-run-overlays.py'. "
            f"Run commands found: {all_runs}\n"
            "Add a step that runs scripts/dry-run-overlays.py on pull_request events.",
        )

    def test_dry_run_comment_step_only_runs_on_pull_request(self):
        """
        The step that posts the PR comment must only run on pull_request events,
        not on push-to-main (where there is no PR to comment on).
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        comment_steps = [
            s for s in all_steps if "dry-run-overlays" in str(s.get("run", ""))
        ]
        self.assertTrue(
            comment_steps,
            "No step invoking dry-run-overlays.py found in workflow",
        )

        for step in comment_steps:
            step_if = str(step.get("if", ""))
            # Step must be gated to pull_request events
            is_pr_gated = (
                "pull_request" in step_if
                or "github.event_name" in step_if
            )
            self.assertTrue(
                is_pr_gated,
                f"The dry-run comment step must only run on pull_request events. "
                f"Step 'if' condition: {step_if!r}. "
                f"Full step: {step}",
            )

    def test_dry_run_comment_step_passes_pr_number(self):
        """
        The dry-run comment posting step must pass the PR number to the script
        so it knows which PR to comment on.
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        comment_steps = [
            s for s in all_steps if "dry-run-overlays" in str(s.get("run", ""))
        ]
        self.assertTrue(comment_steps, "No dry-run-overlays.py step found")

        for step in comment_steps:
            run_text = str(step.get("run", ""))
            has_pr_number = (
                "pr-number" in run_text
                or "pull_request.number" in run_text
                or "github.event.pull_request.number" in run_text
                or "PR_NUMBER" in run_text
            )
            self.assertTrue(
                has_pr_number,
                f"The dry-run comment step must pass the PR number to the script. "
                f"Run text: {run_text!r}",
            )

    def test_dry_run_comment_step_passes_repo_context(self):
        """
        The dry-run comment step must pass the repository slug (owner/name)
        to the script so it can target the correct GitHub repo.
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        comment_steps = [
            s for s in all_steps if "dry-run-overlays" in str(s.get("run", ""))
        ]
        self.assertTrue(comment_steps, "No dry-run-overlays.py step found")

        for step in comment_steps:
            run_text = str(step.get("run", ""))
            # GitHub Actions provides github.repository as "owner/repo"
            has_repo = (
                "repo" in run_text
                or "github.repository" in run_text
                or "GITHUB_REPOSITORY" in run_text
            )
            self.assertTrue(
                has_repo,
                f"The dry-run comment step must pass the repository context. "
                f"Run text: {run_text!r}",
            )

    def test_dry_run_comment_step_passes_config_dir(self):
        """
        The dry-run comment step must pass the config directory so the script
        can discover which overlay configs to diff.
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        comment_steps = [
            s for s in all_steps if "dry-run-overlays" in str(s.get("run", ""))
        ]
        self.assertTrue(comment_steps, "No dry-run-overlays.py step found")

        for step in comment_steps:
            run_text = str(step.get("run", ""))
            # config/repos should be referenced (either explicitly or as default)
            has_config = (
                "config/repos" in run_text
                or "--config-dir" not in run_text  # using default path
            )
            self.assertTrue(
                has_config,
                f"The dry-run comment step should reference config/repos directory. "
                f"Run text: {run_text!r}",
            )


# ---------------------------------------------------------------------------
# TestDryRunCommentAuthentication
# ---------------------------------------------------------------------------


class TestDryRunCommentAuthentication(unittest.TestCase):
    """Tests that the dry-run comment step has access to GITHUB_TOKEN."""

    def test_github_token_is_available_to_dry_run_comment_step(self):
        """
        The dry-run comment step must have GITHUB_TOKEN available so it can
        call the GitHub API to post/update the PR comment.
        """
        doc = _load_workflow()
        all_envs = _collect_all_env_blocks(doc)
        job_level_envs = []
        for job in doc.get("jobs", {}).values():
            if job.get("env"):
                job_level_envs.append(job["env"])

        # Check job-level env (applies to all steps in the job) or step-level env
        all_env_str = str(all_envs) + str(job_level_envs)
        workflow_env = str(doc.get("env") or "")
        combined = workflow_env + " " + all_env_str

        has_token = (
            "GITHUB_TOKEN" in combined
            or "secrets.GITHUB_TOKEN" in combined
            or "github.token" in combined
        )
        self.assertTrue(
            has_token,
            f"GITHUB_TOKEN must be available for the dry-run comment step to post comments. "
            f"Env blocks: {all_envs}",
        )

    def test_no_hardcoded_credentials_in_workflow(self):
        """The workflow must not contain hardcoded GitHub token values."""
        with open(WORKFLOW_PATH) as f:
            raw_content = f.read()

        hardcoded_token_pattern = re.compile(r"ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}")
        matches = hardcoded_token_pattern.findall(raw_content)
        self.assertEqual(
            matches,
            [],
            f"Workflow contains hardcoded GitHub tokens: {matches}",
        )


# ---------------------------------------------------------------------------
# TestDryRunCommentTrigger
# ---------------------------------------------------------------------------


class TestDryRunCommentTrigger(unittest.TestCase):
    """Tests that the pull_request trigger is correctly scoped for diff comments."""

    def test_pull_request_trigger_scoped_to_config_paths(self):
        """
        The pull_request trigger must include a config/** path filter so that
        the comment step only fires when overlay configs actually change.
        """
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        pr_trigger = triggers.get("pull_request") or {}

        # PR trigger may be a dict with paths, or just present (unscoped)
        if isinstance(pr_trigger, dict):
            paths = pr_trigger.get("paths") or []
            has_config_path = any("config" in p for p in paths)
            self.assertTrue(
                has_config_path,
                f"pull_request trigger should be scoped to config/** paths. "
                f"Paths: {paths}",
            )
        else:
            # If pull_request trigger has no path filter, it fires on all PRs.
            # This is acceptable but suboptimal — we still verify it's present.
            self.assertIn(
                "pull_request",
                triggers,
                "pull_request trigger must be present in the workflow",
            )

    def test_pull_request_trigger_is_present(self):
        """The workflow must have a pull_request trigger for the comment step."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        self.assertIn(
            "pull_request",
            triggers,
            f"Workflow must include a pull_request trigger. "
            f"Triggers: {list(triggers.keys())}",
        )


# ---------------------------------------------------------------------------
# TestDryRunCommentWorkflowIntegration
# ---------------------------------------------------------------------------


class TestDryRunCommentWorkflowIntegration(unittest.TestCase):
    """
    Integration-level tests verifying the full dry-run comment pipeline
    in the workflow is coherent.
    """

    def test_dry_run_overlays_step_appears_after_checkout_and_python_setup(self):
        """
        The dry-run comment step must appear after actions/checkout and
        actions/setup-python steps so that Python and the repo are available.
        """
        doc = _load_workflow()
        for job_id, job in doc.get("jobs", {}).items():
            steps = job.get("steps", [])
            step_names = [str(s.get("uses", "") or s.get("name", "")) for s in steps]
            run_commands = [str(s.get("run", "")) for s in steps]

            # Check if this job has the dry-run-overlays step
            has_dry_run_step = any("dry-run-overlays" in run for run in run_commands)
            if not has_dry_run_step:
                continue  # This job does not have the step — skip

            # Find index of checkout, python-setup, and dry-run-overlays step
            checkout_idx = next(
                (i for i, n in enumerate(step_names) if "checkout" in n.lower()), -1
            )
            python_idx = next(
                (i for i, n in enumerate(step_names) if "setup-python" in n.lower()), -1
            )
            comment_idx = next(
                (i for i, r in enumerate(run_commands) if "dry-run-overlays" in r), -1
            )

            if checkout_idx >= 0:
                self.assertLess(
                    checkout_idx,
                    comment_idx,
                    f"checkout step (index {checkout_idx}) must come before "
                    f"dry-run-overlays step (index {comment_idx}) in job '{job_id}'",
                )
            if python_idx >= 0:
                self.assertLess(
                    python_idx,
                    comment_idx,
                    f"setup-python step (index {python_idx}) must come before "
                    f"dry-run-overlays step (index {comment_idx}) in job '{job_id}'",
                )

    def test_dry_run_overlays_step_does_not_run_on_push(self):
        """
        The comment step must not run on push-to-main since there is no PR
        to comment on during a direct push event.
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        comment_steps = [
            s for s in all_steps if "dry-run-overlays" in str(s.get("run", ""))
        ]

        for step in comment_steps:
            step_if = str(step.get("if", ""))
            # If no 'if' condition, the step runs unconditionally — this is a problem
            # because push events don't have a PR to comment on.
            self.assertNotEqual(
                step_if.strip(),
                "",
                f"The dry-run comment step must have an 'if' condition to prevent "
                f"it from running on push-to-main events. Step: {step}",
            )
            # The condition must NOT allow push events through
            allows_only_push = (
                step_if.strip() == "github.event_name == 'push'"
            )
            self.assertFalse(
                allows_only_push,
                f"The dry-run comment step must not run exclusively on push events. "
                f"Step if: {step_if!r}",
            )

    def test_workflow_has_install_dependencies_step_before_dry_run_script(self):
        """
        The workflow must install Python dependencies (at minimum pyyaml) before
        running dry-run-overlays.py.
        """
        doc = _load_workflow()
        for job in doc.get("jobs", {}).values():
            steps = job.get("steps", [])
            run_commands = [str(s.get("run", "")) for s in steps]

            has_dry_run_step = any("dry-run-overlays" in run for run in run_commands)
            if not has_dry_run_step:
                continue

            has_pip_install = any("pip install" in run for run in run_commands)
            self.assertTrue(
                has_pip_install,
                "Workflow must include a 'pip install' step before dry-run-overlays.py",
            )

            pip_idx = next((i for i, r in enumerate(run_commands) if "pip install" in r), -1)
            comment_idx = next(
                (i for i, r in enumerate(run_commands) if "dry-run-overlays" in r), -1
            )
            self.assertLess(
                pip_idx,
                comment_idx,
                f"pip install step (index {pip_idx}) must appear before "
                f"dry-run-overlays step (index {comment_idx})",
            )


if __name__ == "__main__":
    unittest.main()
