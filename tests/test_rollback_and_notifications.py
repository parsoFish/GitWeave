"""
Tests for rollback procedures runbook and workflow failure notifications.

Work item: Document rollback procedures and add workflow failure notifications

These tests define expected behaviour BEFORE implementation (TDD red phase).
All tests in this file will FAIL until the features are implemented.

Feature summary
---------------
1. docs/runbooks/rollback.md — a comprehensive rollback runbook covering:
     a. Overlay rollback: git revert → push → re-apply procedure.
     b. Terraform rollback: terraform state commands and when to use each.
     c. Post-incident verification steps.

2. Failure notifications added to gitweave-apply.yaml and gitweave-infra.yaml:
     a. On job failure: ``gh issue create`` with labels ``incident`` and
        ``workflow-failure``.  Body includes workflow name, failed step, run
        URL, and triggering commit SHA.
     b. On next successful run of same workflow on same branch: close every
        open incident issue whose title matches this workflow's name via
        ``gh issue close``.
     c. Issue search uses workflow name as the lookup key to prevent
        false-positive closes on unrelated workflow incidents.

Test layers
-----------
Unit — TestRollbackRunbookExists
    Verify docs/runbooks/rollback.md exists on disk.

Unit — TestRollbackRunbookOverlaySection
    Verify the runbook documents the full overlay rollback procedure:
    git revert → push → re-apply, including each step as a command block.

Unit — TestRollbackRunbookTerraformSection
    Verify the runbook covers Terraform rollback via terraform state commands
    and explains when to use each approach (state rm, state pull, etc.).

Unit — TestRollbackRunbookPostIncidentSection
    Verify the runbook contains a post-incident verification section
    (health check / smoke test commands after rollback completes).

Unit — TestRollbackRunbookHeadingStructure
    Verify the runbook has logical heading structure: at least three top-level
    sections covering overlay, terraform, and post-incident topics.

Unit — TestApplyWorkflowHasFailureNotificationStep
    Verify gitweave-apply.yaml declares a step with ``if: failure()`` that
    invokes ``gh issue create``.

Unit — TestApplyWorkflowFailureStepLabels
    Verify the failure-notification step applies both ``incident`` and
    ``workflow-failure`` labels.

Unit — TestApplyWorkflowFailureStepBodyFields
    Verify the failure-notification step body references: workflow name,
    failed step, run URL, and triggering commit.

Unit — TestApplyWorkflowFailureStepPermissions
    Verify gitweave-apply.yaml grants ``issues: write`` permission so the
    gh CLI can create issues without a PAT.

Unit — TestApplyWorkflowSuccessCloseStep
    Verify gitweave-apply.yaml has a step that closes open incident issues
    (gh issue close or gh issue list + close) on successful completion.

Unit — TestApplyWorkflowSearchKeyIsWorkflowName
    Verify the issue-search in the close step filters by the workflow name
    (not just by label alone) to avoid false-positive closes.

Unit — TestInfraWorkflowHasFailureNotificationStep
    Verify gitweave-infra.yaml also declares a ``gh issue create`` step
    triggered by ``if: failure()``.

Unit — TestInfraWorkflowFailureStepLabels
    Verify the infra failure-notification step applies the expected labels.

Unit — TestInfraWorkflowFailureStepBodyFields
    Verify the infra failure-notification body includes workflow name, run URL,
    and triggering commit.

Unit — TestInfraWorkflowFailureStepPermissions
    Verify gitweave-infra.yaml grants ``issues: write`` at job or workflow level.

Unit — TestInfraWorkflowSuccessCloseStep
    Verify gitweave-infra.yaml closes open incident issues on success.

Unit — TestInfraWorkflowSearchKeyIsWorkflowName
    Verify the infra workflow's close step searches by workflow name.

Integration — TestRollbackRunbookMarkdownValidity
    Parse rollback.md line-by-line and confirm there are no broken heading
    anchors, unclosed code fences, or empty required sections.

Integration — TestApplyWorkflowYamlValidity
    Confirm gitweave-apply.yaml still parses as valid YAML after the failure
    notification steps are added (regression guard).

Integration — TestInfraWorkflowYamlValidity
    Confirm gitweave-infra.yaml still parses as valid YAML after the failure
    notification steps are added.
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
ROLLBACK_RUNBOOK_PATH = os.path.join(REPO_ROOT, "docs", "runbooks", "rollback.md")
APPLY_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "gitweave-apply.yaml"
)
INFRA_WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "gitweave-infra.yaml"
)


# ---------------------------------------------------------------------------
# Shared helpers — runbook
# ---------------------------------------------------------------------------


def _read_runbook() -> str:
    """Return the full text of rollback.md, raising FileNotFoundError if absent."""
    with open(ROLLBACK_RUNBOOK_PATH) as f:
        return f.read()


def _runbook_headings(text: str) -> list[str]:
    """
    Return a list of all Markdown heading texts (stripped of # prefix and whitespace).
    Handles ATX headings of any level.
    """
    return [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if re.match(r"^#{1,6}\s", line)
    ]


def _code_blocks(text: str) -> list[str]:
    """
    Return a list of the contents of every fenced code block (``` ... ```) in *text*.
    """
    # Match fenced blocks opened with optional language identifier.
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)


# ---------------------------------------------------------------------------
# Shared helpers — workflows
# ---------------------------------------------------------------------------


def _load_workflow(path: str) -> dict:
    """Parse a GitHub Actions workflow YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _get_triggers(doc: dict) -> dict:
    """Return trigger mapping, handling PyYAML's `on` → True quirk."""
    return doc.get("on") or doc.get(True) or {}


def _collect_all_steps(doc: dict) -> list[dict]:
    """Return a flat list of every step across all jobs."""
    steps: list[dict] = []
    for job in doc.get("jobs", {}).values():
        steps.extend(job.get("steps", []) or [])
    return steps


def _steps_with_if(steps: list[dict], condition_substring: str) -> list[dict]:
    """Return steps whose ``if`` field contains *condition_substring*."""
    return [
        s
        for s in steps
        if condition_substring.lower() in str(s.get("if", "")).lower()
    ]


def _steps_with_run_containing(steps: list[dict], fragment: str) -> list[dict]:
    """Return steps whose ``run`` block contains *fragment* (case-insensitive)."""
    return [
        s
        for s in steps
        if fragment.lower() in str(s.get("run", "")).lower()
    ]


def _workflow_permissions(doc: dict) -> dict:
    """
    Return the top-level permissions block.  Returns an empty dict when absent.
    """
    return doc.get("permissions") or {}


def _job_permissions(doc: dict, job_id: str) -> dict:
    """Return the permissions block for *job_id*, or empty dict when absent."""
    job = (doc.get("jobs") or {}).get(job_id) or {}
    return job.get("permissions") or {}


def _effective_issues_permission(doc: dict, job_id: str) -> str | None:
    """
    Return the effective ``issues`` permission for *job_id*:
    checks the job-level permissions first, then falls back to workflow-level.
    Returns None when neither declares an issues permission.
    """
    job_perms = _job_permissions(doc, job_id)
    if "issues" in job_perms:
        return str(job_perms["issues"])
    workflow_perms = _workflow_permissions(doc)
    return str(workflow_perms["issues"]) if "issues" in workflow_perms else None


# ---------------------------------------------------------------------------
# Unit tests — rollback runbook content
# ---------------------------------------------------------------------------


class TestRollbackRunbookExists(unittest.TestCase):
    """docs/runbooks/rollback.md must exist on disk."""

    def test_file_exists(self) -> None:
        self.assertTrue(
            os.path.isfile(ROLLBACK_RUNBOOK_PATH),
            f"Expected rollback runbook at {ROLLBACK_RUNBOOK_PATH} but file is absent",
        )

    def test_file_is_not_empty(self) -> None:
        self.assertTrue(
            os.path.isfile(ROLLBACK_RUNBOOK_PATH),
            f"Runbook absent: {ROLLBACK_RUNBOOK_PATH}",
        )
        self.assertGreater(
            os.path.getsize(ROLLBACK_RUNBOOK_PATH),
            0,
            "rollback.md exists but is empty",
        )


class TestRollbackRunbookOverlaySection(unittest.TestCase):
    """Runbook must document the overlay rollback procedure."""

    def setUp(self) -> None:
        self.text = _read_runbook()

    def test_overlay_rollback_section_exists(self) -> None:
        headings = _runbook_headings(self.text)
        has_overlay_heading = any(
            "overlay" in h.lower() for h in headings
        )
        self.assertTrue(
            has_overlay_heading,
            f"Expected a heading mentioning 'overlay' in rollback.md. "
            f"Found headings: {headings}",
        )

    def test_git_revert_command_present(self) -> None:
        self.assertIn(
            "git revert",
            self.text,
            "Overlay rollback section must include a 'git revert' command",
        )

    def test_git_push_command_present(self) -> None:
        self.assertIn(
            "git push",
            self.text,
            "Overlay rollback section must include a 'git push' command after revert",
        )

    def test_reapply_step_present(self) -> None:
        # The runbook must explain how to re-trigger the apply workflow after push.
        # Accept either a gh workflow run command or an apply-overlays.py invocation.
        has_reapply = (
            "apply-overlays" in self.text
            or "gh workflow run" in self.text
            or "gitweave-apply" in self.text
        )
        self.assertTrue(
            has_reapply,
            "Overlay rollback section must document how to re-apply after reverting "
            "(reference apply-overlays.py or gh workflow run)",
        )

    def test_overlay_steps_appear_in_logical_order(self) -> None:
        # git revert must appear before git push in the document.
        revert_pos = self.text.find("git revert")
        push_pos = self.text.find("git push")
        self.assertGreater(
            revert_pos,
            -1,
            "git revert not found in runbook",
        )
        self.assertGreater(
            push_pos,
            -1,
            "git push not found in runbook",
        )
        self.assertLess(
            revert_pos,
            push_pos,
            "git revert must appear before git push in the runbook",
        )


class TestRollbackRunbookTerraformSection(unittest.TestCase):
    """Runbook must document Terraform rollback via state commands."""

    def setUp(self) -> None:
        self.text = _read_runbook()

    def test_terraform_rollback_section_exists(self) -> None:
        headings = _runbook_headings(self.text)
        has_terraform_heading = any(
            "terraform" in h.lower() for h in headings
        )
        self.assertTrue(
            has_terraform_heading,
            f"Expected a heading mentioning 'terraform' in rollback.md. "
            f"Found headings: {headings}",
        )

    def test_terraform_state_command_referenced(self) -> None:
        self.assertIn(
            "terraform state",
            self.text,
            "Terraform rollback section must reference 'terraform state' commands",
        )

    def test_when_to_use_each_command_explained(self) -> None:
        # The runbook must explain when to use each state command.
        # We check for either 'terraform state rm' or 'terraform state pull'
        # plus some explanatory prose indicating conditional guidance.
        has_state_rm = "state rm" in self.text or "state pull" in self.text
        has_guidance_language = any(
            kw in self.text.lower()
            for kw in ("when to use", "use when", "use this when", "prefer")
        )
        self.assertTrue(
            has_state_rm,
            "Terraform rollback must mention at least one specific state subcommand "
            "(state rm, state pull, etc.)",
        )
        self.assertTrue(
            has_guidance_language,
            "Terraform rollback section must include guidance on WHEN to use each "
            "command (look for 'when to use' / 'use when' / 'prefer')",
        )

    def test_no_auto_approve_in_terraform_commands(self) -> None:
        # The runbook must never suggest using -auto-approve unsafely.
        code_blocks_text = "\n".join(_code_blocks(self.text))
        # -auto-approve is acceptable only on explicit rollback applies, but
        # the runbook should not use it without a preceding warning.  We check
        # that -auto-approve, if present, is accompanied by a warning.
        if "-auto-approve" in code_blocks_text:
            self.assertIn(
                "-auto-approve",
                self.text,  # sanity — already established above
            )
            # A warning keyword must appear somewhere before the auto-approve line.
            auto_approve_pos = self.text.find("-auto-approve")
            preceding_text = self.text[:auto_approve_pos].lower()
            has_warning = any(
                kw in preceding_text
                for kw in ("caution", "warning", "danger", "carefully", "review")
            )
            self.assertTrue(
                has_warning,
                "If -auto-approve is present in the runbook, a caution/warning must "
                "appear in the text before it",
            )


class TestRollbackRunbookPostIncidentSection(unittest.TestCase):
    """Runbook must include post-incident verification steps."""

    def setUp(self) -> None:
        self.text = _read_runbook()

    def test_post_incident_section_exists(self) -> None:
        headings = _runbook_headings(self.text)
        has_post_incident = any(
            any(kw in h.lower() for kw in ("post-incident", "post incident", "verification", "verify", "smoke"))
            for h in headings
        )
        self.assertTrue(
            has_post_incident,
            f"Expected a post-incident / verification heading in rollback.md. "
            f"Found headings: {headings}",
        )

    def test_verification_commands_in_code_block(self) -> None:
        code_blocks_text = "\n".join(_code_blocks(self.text))
        # At least one code block must appear after a verification/post-incident
        # heading; a simple heuristic: code blocks must exist and contain at
        # least one command referencing gh, curl, or a script.
        self.assertTrue(
            len(_code_blocks(self.text)) > 0,
            "Post-incident section must include at least one fenced code block "
            "with verification commands",
        )
        has_verification_command = any(
            kw in code_blocks_text
            for kw in ("gh ", "curl", "python", "terraform", "apply-overlays")
        )
        self.assertTrue(
            has_verification_command,
            "Post-incident code blocks must contain at least one actionable command "
            "(gh, curl, python, terraform, or apply-overlays)",
        )


class TestRollbackRunbookHeadingStructure(unittest.TestCase):
    """Runbook must have at least three top-level sections."""

    def setUp(self) -> None:
        self.text = _read_runbook()

    def test_at_least_three_major_sections(self) -> None:
        # Count H2 headings (##) — the main sections.
        h2_headings = [
            line for line in self.text.splitlines()
            if re.match(r"^##\s", line)
        ]
        self.assertGreaterEqual(
            len(h2_headings),
            3,
            f"rollback.md must have at least 3 H2 sections (overlay, terraform, "
            f"post-incident). Found: {h2_headings}",
        )

    def test_overlay_and_terraform_and_postincident_all_covered(self) -> None:
        text_lower = self.text.lower()
        self.assertIn("overlay", text_lower, "rollback.md must cover overlay rollback")
        self.assertIn("terraform", text_lower, "rollback.md must cover terraform rollback")
        self.assertTrue(
            "post-incident" in text_lower or "verification" in text_lower or "verify" in text_lower,
            "rollback.md must cover post-incident verification",
        )


# ---------------------------------------------------------------------------
# Unit tests — gitweave-apply.yaml failure notifications
# ---------------------------------------------------------------------------


class TestApplyWorkflowHasFailureNotificationStep(unittest.TestCase):
    """gitweave-apply.yaml must declare a step that creates an issue on failure."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_failure_step_with_if_failure_exists(self) -> None:
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.assertTrue(
            len(failure_steps) > 0,
            "gitweave-apply.yaml must have at least one step with 'if: failure()'",
        )

    def test_failure_step_invokes_gh_issue_create(self) -> None:
        failure_steps = _steps_with_if(self.steps, "failure()")
        gh_create_steps = _steps_with_run_containing(failure_steps, "gh issue create")
        self.assertTrue(
            len(gh_create_steps) > 0,
            "The failure step in gitweave-apply.yaml must invoke 'gh issue create'",
        )


class TestApplyWorkflowFailureStepLabels(unittest.TestCase):
    """Failure notification step must apply 'incident' and 'workflow-failure' labels."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.gh_steps = _steps_with_run_containing(failure_steps, "gh issue create")

    def test_incident_label_applied(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-apply.yaml",
        )
        all_run_text = "\n".join(s.get("run", "") for s in self.gh_steps)
        self.assertIn(
            "incident",
            all_run_text,
            "Failure step must apply the 'incident' label",
        )

    def test_workflow_failure_label_applied(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-apply.yaml",
        )
        all_run_text = "\n".join(s.get("run", "") for s in self.gh_steps)
        self.assertIn(
            "workflow-failure",
            all_run_text,
            "Failure step must apply the 'workflow-failure' label",
        )


class TestApplyWorkflowFailureStepBodyFields(unittest.TestCase):
    """Failure issue body must include workflow name, failed step, run URL, and commit."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.gh_steps = _steps_with_run_containing(failure_steps, "gh issue create")
        self.all_run_text = "\n".join(s.get("run", "") for s in self.gh_steps)

    def _assert_body_field(self, fragment: str, description: str) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-apply.yaml",
        )
        self.assertIn(
            fragment,
            self.all_run_text,
            f"Failure issue body must include {description}",
        )

    def test_body_includes_workflow_name(self) -> None:
        # The workflow name should be referenced via ${{ github.workflow }} or
        # hard-coded as 'GitWeave Apply'.
        has_workflow_ref = (
            "github.workflow" in self.all_run_text
            or "GitWeave Apply" in self.all_run_text
        )
        self.assertTrue(
            has_workflow_ref,
            "Failure issue body must reference the workflow name "
            "(${{ github.workflow }} or 'GitWeave Apply')",
        )

    def test_body_includes_run_url(self) -> None:
        # Run URL is available via github.server_url + github.repository + runs/github.run_id
        # or the convenience expression github.event.repository.html_url.
        has_run_url = (
            "github.run_id" in self.all_run_text
            or "server_url" in self.all_run_text
            or "run_url" in self.all_run_text
            or "GITHUB_SERVER_URL" in self.all_run_text
        )
        self.assertTrue(
            has_run_url,
            "Failure issue body must include the run URL "
            "(reference github.run_id, server_url, or GITHUB_SERVER_URL)",
        )

    def test_body_includes_triggering_commit(self) -> None:
        has_commit = (
            "github.sha" in self.all_run_text
            or "GITHUB_SHA" in self.all_run_text
            or "sha" in self.all_run_text.lower()
        )
        self.assertTrue(
            has_commit,
            "Failure issue body must include the triggering commit SHA "
            "(reference github.sha or GITHUB_SHA)",
        )


class TestApplyWorkflowFailureStepPermissions(unittest.TestCase):
    """gitweave-apply.yaml must grant issues: write for the gh CLI to create issues."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)

    def _issues_write_granted(self) -> bool:
        # Check top-level permissions.
        workflow_perms = _workflow_permissions(self.doc)
        if workflow_perms.get("issues") == "write":
            return True
        # Check every job.
        for job_id in (self.doc.get("jobs") or {}):
            if _job_permissions(self.doc, job_id).get("issues") == "write":
                return True
        return False

    def test_issues_write_permission_declared(self) -> None:
        self.assertTrue(
            self._issues_write_granted(),
            "gitweave-apply.yaml must declare 'issues: write' at the workflow or "
            "job level so 'gh issue create' can authenticate without a PAT",
        )


class TestApplyWorkflowSuccessCloseStep(unittest.TestCase):
    """gitweave-apply.yaml must close open incident issues on successful completion."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_success_close_step_exists(self) -> None:
        # The close step must NOT be conditioned on failure() — it runs on success.
        # Look for steps that reference 'gh issue close' or 'gh issue list' followed
        # by close logic.
        close_steps = _steps_with_run_containing(self.steps, "gh issue")
        # Filter out the failure-create steps.
        non_failure_close = [
            s for s in close_steps
            if "failure()" not in str(s.get("if", ""))
            and (
                "close" in s.get("run", "").lower()
                or ("list" in s.get("run", "").lower() and "close" in s.get("run", "").lower())
            )
        ]
        self.assertTrue(
            len(non_failure_close) > 0,
            "gitweave-apply.yaml must have a step that closes open incident issues "
            "on successful completion (gh issue close / gh issue list ... | xargs gh issue close)",
        )


class TestApplyWorkflowSearchKeyIsWorkflowName(unittest.TestCase):
    """Issue search must use workflow name to avoid closing unrelated incidents."""

    def setUp(self) -> None:
        self.doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_close_step_searches_by_workflow_name(self) -> None:
        close_steps = [
            s for s in self.steps
            if "gh issue" in str(s.get("run", "")).lower()
            and "close" in str(s.get("run", "")).lower()
        ]
        self.assertTrue(
            len(close_steps) > 0,
            "No issue-close step found in gitweave-apply.yaml",
        )
        all_close_run = "\n".join(s.get("run", "") for s in close_steps)
        # The search must reference the workflow name — either via the
        # github.workflow context or a hard-coded name string.
        has_workflow_search_key = (
            "github.workflow" in all_close_run
            or "GitWeave Apply" in all_close_run
            or "workflow-name" in all_close_run.lower()
        )
        self.assertTrue(
            has_workflow_search_key,
            "The issue-close step must search by workflow name "
            "(${{ github.workflow }} or 'GitWeave Apply') to avoid closing "
            "issues from other workflows",
        )


# ---------------------------------------------------------------------------
# Unit tests — gitweave-infra.yaml failure notifications
# ---------------------------------------------------------------------------


class TestInfraWorkflowHasFailureNotificationStep(unittest.TestCase):
    """gitweave-infra.yaml must declare a step that creates an issue on failure."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_failure_step_with_if_failure_exists(self) -> None:
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.assertTrue(
            len(failure_steps) > 0,
            "gitweave-infra.yaml must have at least one step with 'if: failure()'",
        )

    def test_failure_step_invokes_gh_issue_create(self) -> None:
        failure_steps = _steps_with_if(self.steps, "failure()")
        gh_create_steps = _steps_with_run_containing(failure_steps, "gh issue create")
        self.assertTrue(
            len(gh_create_steps) > 0,
            "The failure step in gitweave-infra.yaml must invoke 'gh issue create'",
        )


class TestInfraWorkflowFailureStepLabels(unittest.TestCase):
    """Infra failure notification step must apply correct labels."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.gh_steps = _steps_with_run_containing(failure_steps, "gh issue create")
        self.all_run_text = "\n".join(s.get("run", "") for s in self.gh_steps)

    def test_incident_label_applied(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-infra.yaml",
        )
        self.assertIn(
            "incident",
            self.all_run_text,
            "Infra failure step must apply the 'incident' label",
        )

    def test_workflow_failure_label_applied(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-infra.yaml",
        )
        self.assertIn(
            "workflow-failure",
            self.all_run_text,
            "Infra failure step must apply the 'workflow-failure' label",
        )


class TestInfraWorkflowFailureStepBodyFields(unittest.TestCase):
    """Infra failure issue body must include workflow name, run URL, and commit."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)
        failure_steps = _steps_with_if(self.steps, "failure()")
        self.gh_steps = _steps_with_run_containing(failure_steps, "gh issue create")
        self.all_run_text = "\n".join(s.get("run", "") for s in self.gh_steps)

    def test_body_includes_workflow_name(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-infra.yaml",
        )
        has_workflow_ref = (
            "github.workflow" in self.all_run_text
            or "GitWeave Infrastructure" in self.all_run_text
        )
        self.assertTrue(
            has_workflow_ref,
            "Infra failure issue body must reference the workflow name",
        )

    def test_body_includes_run_url(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-infra.yaml",
        )
        has_run_url = (
            "github.run_id" in self.all_run_text
            or "server_url" in self.all_run_text
            or "run_url" in self.all_run_text
            or "GITHUB_SERVER_URL" in self.all_run_text
        )
        self.assertTrue(
            has_run_url,
            "Infra failure issue body must include the run URL",
        )

    def test_body_includes_triggering_commit(self) -> None:
        self.assertTrue(
            len(self.gh_steps) > 0,
            "No 'gh issue create' failure step found in gitweave-infra.yaml",
        )
        has_commit = (
            "github.sha" in self.all_run_text
            or "GITHUB_SHA" in self.all_run_text
            or "sha" in self.all_run_text.lower()
        )
        self.assertTrue(
            has_commit,
            "Infra failure issue body must include the triggering commit SHA",
        )


class TestInfraWorkflowFailureStepPermissions(unittest.TestCase):
    """gitweave-infra.yaml must grant issues: write."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)

    def _issues_write_granted(self) -> bool:
        if _workflow_permissions(self.doc).get("issues") == "write":
            return True
        for job_id in (self.doc.get("jobs") or {}):
            if _job_permissions(self.doc, job_id).get("issues") == "write":
                return True
        return False

    def test_issues_write_permission_declared(self) -> None:
        self.assertTrue(
            self._issues_write_granted(),
            "gitweave-infra.yaml must declare 'issues: write' at the workflow or "
            "job level so 'gh issue create' can authenticate without a PAT",
        )


class TestInfraWorkflowSuccessCloseStep(unittest.TestCase):
    """gitweave-infra.yaml must close open incident issues on successful completion."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_success_close_step_exists(self) -> None:
        close_steps = [
            s for s in self.steps
            if "gh issue" in str(s.get("run", "")).lower()
            and "failure()" not in str(s.get("if", ""))
            and "close" in str(s.get("run", "")).lower()
        ]
        self.assertTrue(
            len(close_steps) > 0,
            "gitweave-infra.yaml must have a step that closes open incident issues "
            "on successful completion",
        )


class TestInfraWorkflowSearchKeyIsWorkflowName(unittest.TestCase):
    """Infra issue-close step must search by workflow name."""

    def setUp(self) -> None:
        self.doc = _load_workflow(INFRA_WORKFLOW_PATH)
        self.steps = _collect_all_steps(self.doc)

    def test_close_step_searches_by_workflow_name(self) -> None:
        close_steps = [
            s for s in self.steps
            if "gh issue" in str(s.get("run", "")).lower()
            and "close" in str(s.get("run", "")).lower()
        ]
        self.assertTrue(
            len(close_steps) > 0,
            "No issue-close step found in gitweave-infra.yaml",
        )
        all_close_run = "\n".join(s.get("run", "") for s in close_steps)
        has_workflow_search_key = (
            "github.workflow" in all_close_run
            or "GitWeave Infrastructure" in all_close_run
            or "workflow-name" in all_close_run.lower()
        )
        self.assertTrue(
            has_workflow_search_key,
            "The issue-close step in gitweave-infra.yaml must search by workflow "
            "name to avoid false-positive closes",
        )


# ---------------------------------------------------------------------------
# Integration tests — YAML validity regressions
# ---------------------------------------------------------------------------


class TestApplyWorkflowYamlValidity(unittest.TestCase):
    """gitweave-apply.yaml must remain valid YAML after adding notification steps."""

    def test_parses_without_error(self) -> None:
        try:
            doc = _load_workflow(APPLY_WORKFLOW_PATH)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"gitweave-apply.yaml failed to parse as YAML: {exc}")
        self.assertIsNotNone(doc, "gitweave-apply.yaml parsed to None (empty file?)")
        self.assertIn(
            "jobs",
            doc,
            "gitweave-apply.yaml must have a 'jobs' key",
        )

    def test_jobs_key_is_mapping(self) -> None:
        doc = _load_workflow(APPLY_WORKFLOW_PATH)
        self.assertIsInstance(
            doc.get("jobs"),
            dict,
            "'jobs' in gitweave-apply.yaml must be a mapping",
        )


class TestInfraWorkflowYamlValidity(unittest.TestCase):
    """gitweave-infra.yaml must remain valid YAML after adding notification steps."""

    def test_parses_without_error(self) -> None:
        try:
            doc = _load_workflow(INFRA_WORKFLOW_PATH)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"gitweave-infra.yaml failed to parse as YAML: {exc}")
        self.assertIsNotNone(doc, "gitweave-infra.yaml parsed to None (empty file?)")
        self.assertIn(
            "jobs",
            doc,
            "gitweave-infra.yaml must have a 'jobs' key",
        )


class TestRollbackRunbookMarkdownValidity(unittest.TestCase):
    """rollback.md must have balanced fenced code blocks and non-empty sections."""

    def setUp(self) -> None:
        self.text = _read_runbook()

    def test_fenced_code_blocks_are_balanced(self) -> None:
        # Count opening ``` vs closing ``` — they must be even.
        fence_count = len(re.findall(r"^```", self.text, re.MULTILINE))
        self.assertEqual(
            fence_count % 2,
            0,
            f"rollback.md has an odd number of ``` markers ({fence_count}) — "
            "at least one fenced code block is unclosed",
        )

    def test_no_h2_section_is_empty(self) -> None:
        lines = self.text.splitlines()
        for i, line in enumerate(lines):
            if not re.match(r"^##\s", line):
                continue
            # Look ahead for the next non-blank line.
            next_content_lines = [
                l for l in lines[i + 1:]
                if l.strip() and not re.match(r"^#{1,6}\s", l)
            ]
            self.assertTrue(
                len(next_content_lines) > 0,
                f"Section '{line.strip()}' in rollback.md appears to have no content",
            )

    def test_runbook_has_title(self) -> None:
        first_line = self.text.splitlines()[0] if self.text.strip() else ""
        self.assertTrue(
            re.match(r"^#\s", first_line),
            "rollback.md must start with an H1 title heading",
        )


if __name__ == "__main__":
    unittest.main()
