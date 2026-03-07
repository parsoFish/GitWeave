"""
Tests for the PR comment posting step added to the plan job in gitweave-infra.yaml.

The plan job must post the terraform plan output as a collapsible GitHub PR comment
after every plan run on a pull_request event. Subsequent pushes to the same PR
must UPDATE the existing comment rather than creating a new one.

Acceptance criteria under test:
  - plan job has pull-requests: write permission (job or workflow level)
  - A post-plan step posts a PR comment using gh CLI (GitHub REST API)
  - Comment body uses <details><summary>Terraform Plan (exit N)</summary>...</details> format
  - Comment includes the workflow run URL ($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID)
  - Comment includes the triggering commit SHA ($GITHUB_SHA)
  - Comment body includes a unique marker so subsequent runs can find and update it
  - Update logic uses 'gh api --method PATCH' (not POST) when existing comment found
  - Plan output is truncated at 65000 characters with '\\n...\\n[Output truncated]' suffix
  - No comment is posted when terraform plan exit code indicates no changes (exit 0 with no diff)
  - Comment step only runs on pull_request events (not push/merge to main)

All tests FAIL until the plan job in .github/workflows/gitweave-infra.yaml is
extended to satisfy the acceptance criteria (TDD red phase).
"""

import os
import re
import textwrap
import unittest

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "gitweave-infra.yaml")


# ---------------------------------------------------------------------------
# Shared helpers (mirror conventions from test_infra_workflow_gates.py)
# ---------------------------------------------------------------------------


def _load_workflow() -> dict:
    """Parse gitweave-infra.yaml and return the document dict."""
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def _get_triggers(doc: dict) -> dict:
    """
    Return the workflow trigger mapping.
    Handles PyYAML's YAML 1.1 quirk where bare `on:` is parsed as boolean True.
    """
    return doc.get("on") or doc.get(True) or {}


def _find_job(doc: dict, job_id: str) -> dict | None:
    """Return a job dict by exact job id, or None if not found."""
    return doc.get("jobs", {}).get(job_id)


def _plan_job_steps(doc: dict) -> list[dict]:
    """Return all steps for the plan job, or empty list."""
    job = _find_job(doc, "plan")
    if job is None:
        return []
    return job.get("steps", []) or []


def _step_run_text(step: dict) -> str:
    """Return the run: value of a step as a string, or empty string."""
    return str(step.get("run", "") or "")


def _all_run_text_in_job(steps: list[dict]) -> str:
    """Concatenate all run: values from a list of steps."""
    return "\n".join(_step_run_text(s) for s in steps)


def _find_steps_by_name_keyword(steps: list[dict], keyword: str) -> list[dict]:
    """Return steps whose name contains keyword (case-insensitive)."""
    kw = keyword.lower()
    return [s for s in steps if kw in str(s.get("name", "")).lower()]


def _find_steps_by_run_pattern(steps: list[dict], pattern: str) -> list[dict]:
    """Return steps whose run: text matches the given regex pattern."""
    return [s for s in steps if re.search(pattern, _step_run_text(s))]


# ---------------------------------------------------------------------------
# Helpers for permission resolution
# ---------------------------------------------------------------------------


def _effective_plan_permissions(doc: dict) -> dict:
    """
    Return the merged permissions visible to the plan job.
    Job-level permissions override workflow-level for the same key.
    """
    workflow_perms = doc.get("permissions") or {}
    plan_job = _find_job(doc, "plan")
    job_perms = (plan_job or {}).get("permissions") or {}
    if isinstance(workflow_perms, dict) and isinstance(job_perms, dict):
        return {**workflow_perms, **job_perms}
    if isinstance(job_perms, dict):
        return job_perms
    return workflow_perms if isinstance(workflow_perms, dict) else {}


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestPlanJobHasPullRequestsWritePermission(unittest.TestCase):
    """
    The plan job needs pull-requests: write to create/update PR comments
    via the GITHUB_TOKEN. Without this permission the gh CLI call will 403.
    """

    def setUp(self):
        self.doc = _load_workflow()

    def test_plan_job_grants_pull_requests_write(self):
        """
        plan job (or the workflow) must grant pull-requests: write so that
        the gh CLI can post and update PR comments via the GITHUB_TOKEN.
        """
        perms = _effective_plan_permissions(self.doc)
        self.assertEqual(
            perms.get("pull-requests"),
            "write",
            f"Effective plan job permissions.pull-requests is "
            f"{perms.get('pull-requests')!r}, expected 'write'. "
            "Add 'pull-requests: write' to the plan job permissions block "
            "so the GITHUB_TOKEN can create/update PR comments.",
        )

    def test_workflow_level_permissions_include_pull_requests_write_or_job_does(self):
        """
        Either the workflow-level permissions block or the plan job's own
        permissions block must declare pull-requests: write — at least one
        of the two must set this so the plan job can post comments.
        """
        workflow_perms = self.doc.get("permissions") or {}
        plan_job = _find_job(self.doc, "plan")
        job_perms = (plan_job or {}).get("permissions") or {}

        workflow_grants = (
            isinstance(workflow_perms, dict)
            and workflow_perms.get("pull-requests") == "write"
        )
        job_grants = (
            isinstance(job_perms, dict)
            and job_perms.get("pull-requests") == "write"
        )
        self.assertTrue(
            workflow_grants or job_grants,
            "Neither the workflow-level nor the plan job-level permissions grant "
            "'pull-requests: write'. The comment step will fail with a 403 error "
            "unless this permission is added.",
        )


class TestPlanOutputCaptureStep(unittest.TestCase):
    """
    The plan job must capture terraform plan's text output so it can be
    embedded in the PR comment body. The raw binary tfplan artifact is not
    human-readable; the comment requires the human-readable plan text.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)

    def test_plan_output_captured_to_env_or_file(self):
        """
        A step must capture the terraform plan text output — either by
        redirecting to a file or by writing it to $GITHUB_OUTPUT / $GITHUB_ENV —
        so the PR comment step can embed the plan text in the comment body.
        """
        all_runs = _all_run_text_in_job(self.steps)
        # Accept redirect to file OR GITHUB_OUTPUT / GITHUB_ENV capture patterns
        captured = (
            re.search(r"terraform\s+show", all_runs)
            or re.search(r"terraform\s+plan.*>\s*\S+", all_runs)
            or re.search(r"GITHUB_OUTPUT|GITHUB_ENV", all_runs)
            or re.search(r"plan_output\s*=", all_runs)
        )
        self.assertIsNotNone(
            captured,
            "No step captures the terraform plan text output. "
            "Add a step that runs 'terraform show -no-color tfplan' and captures "
            "the output so it can be embedded in the PR comment body.",
        )

    def test_plan_output_captured_without_color_codes(self):
        """
        Terraform output must be captured with -no-color flag so ANSI escape
        sequences do not pollute the GitHub comment markdown.
        """
        all_runs = _all_run_text_in_job(self.steps)
        has_no_color = "-no-color" in all_runs or "--no-color" in all_runs
        self.assertTrue(
            has_no_color,
            "Plan output capture step is missing the '-no-color' flag. "
            "ANSI color codes will render as literal escape sequences in the "
            "PR comment. Add '-no-color' to the terraform show or plan command.",
        )


class TestPrCommentStepExists(unittest.TestCase):
    """
    A dedicated step must exist in the plan job to post/update the PR comment.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)

    def test_plan_job_has_post_comment_step(self):
        """
        plan job must have a step that posts a PR comment using the gh CLI
        or the GitHub REST API — identified by 'gh api' or 'gh pr comment'
        appearing in its run: block.
        """
        comment_steps = _find_steps_by_run_pattern(
            self.steps, r"gh\s+(api|pr\s+comment)"
        )
        self.assertGreater(
            len(comment_steps),
            0,
            "plan job has no step that posts a PR comment. "
            "Add a step that calls 'gh api repos/.../issues/.../comments' "
            "or 'gh pr comment' to post the plan output as a PR comment.",
        )

    def test_post_comment_step_only_runs_on_pull_request(self):
        """
        The comment step must be guarded by an 'if' condition that checks
        github.event_name == 'pull_request' so it does not attempt to
        post a comment when the workflow fires on a push to main.
        """
        comment_steps = _find_steps_by_run_pattern(
            self.steps, r"gh\s+(api|pr\s+comment)"
        )
        if not comment_steps:
            self.skipTest("No comment step found — caught by previous test")

        for step in comment_steps:
            if_condition = str(step.get("if", "") or "")
            self.assertIn(
                "pull_request",
                if_condition,
                f"Comment step '{step.get('name', '<unnamed>')}' has if: {if_condition!r}. "
                "It must be guarded with a condition like "
                "\"if: github.event_name == 'pull_request'\" to prevent "
                "attempting to post comments on push-to-main events.",
            )


class TestCommentBodyFormat(unittest.TestCase):
    """
    The PR comment body must use the exact collapsible format specified
    in the acceptance criteria.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)
        self.all_runs = _all_run_text_in_job(self.steps)

    def test_comment_uses_details_summary_tags(self):
        """
        Comment body must wrap plan output in HTML <details>/<summary> tags
        to make it collapsible in the GitHub PR interface.
        """
        has_details = "<details>" in self.all_runs or r"\<details\>" in self.all_runs
        self.assertTrue(
            has_details,
            "No '<details>' tag found in any plan job run step. "
            "The PR comment must use a collapsible <details><summary>...</summary>"
            "...</details> block as per the acceptance criteria.",
        )

    def test_comment_summary_includes_terraform_plan_text(self):
        """
        The <summary> element must contain the text 'Terraform Plan' so reviewers
        can identify the collapsed section at a glance.
        """
        has_tf_plan_summary = bool(
            re.search(r"<summary>.*[Tt]erraform\s+[Pp]lan", self.all_runs)
        )
        self.assertTrue(
            has_tf_plan_summary,
            "No '<summary>...Terraform Plan...' text found in plan job steps. "
            "The comment summary must read 'Terraform Plan (exit N)' "
            "so reviewers immediately know what the section contains.",
        )

    def test_comment_summary_includes_exit_code(self):
        """
        The <summary> must include the terraform plan exit code so reviewers
        can see whether the plan has changes without expanding the section.
        Expected pattern: 'Terraform Plan (exit N)' or 'exit code N'.
        """
        has_exit_code = bool(
            re.search(r"exit\s*(code)?\s*[\"']?\$", self.all_runs, re.IGNORECASE)
            or re.search(r"exit\s+\d", self.all_runs, re.IGNORECASE)
            or re.search(r"\(exit\s", self.all_runs, re.IGNORECASE)
        )
        self.assertTrue(
            has_exit_code,
            "Comment summary does not include the plan exit code. "
            "Format it as 'Terraform Plan (exit $EXIT_CODE)' so the exit status "
            "is visible in the collapsed summary line.",
        )

    def test_comment_includes_workflow_run_url(self):
        """
        The comment body must include a link to the workflow run using
        $GITHUB_SERVER_URL, $GITHUB_REPOSITORY, and $GITHUB_RUN_ID environment
        variables so reviewers can jump directly to the full run logs.
        """
        has_run_url = bool(
            re.search(r"GITHUB_SERVER_URL", self.all_runs)
            and re.search(r"GITHUB_RUN_ID", self.all_runs)
        )
        self.assertTrue(
            has_run_url,
            "Comment does not include a workflow run link. "
            "Add '$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID' "
            "to the comment body so reviewers can access the full run logs.",
        )

    def test_comment_includes_commit_sha(self):
        """
        The comment body must reference $GITHUB_SHA (the triggering commit)
        so reviewers know which commit the plan was generated from.
        """
        has_sha = "GITHUB_SHA" in self.all_runs
        self.assertTrue(
            has_sha,
            "Comment does not include the triggering commit SHA. "
            "Add '$GITHUB_SHA' to the comment body to identify the commit "
            "that produced this plan output.",
        )


class TestCommentUniqueMarker(unittest.TestCase):
    """
    The comment must embed a unique HTML marker so subsequent plan runs
    on the same PR can locate and update the comment rather than creating
    a new one. Without a marker, every push would add a new comment.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)
        self.all_runs = _all_run_text_in_job(self.steps)

    def test_comment_body_contains_unique_marker(self):
        """
        The comment body must embed a unique HTML comment marker
        (e.g., '<!-- gitweave-tf-plan -->') so the update step can find
        the existing comment via the GitHub list comments API.
        """
        has_marker = bool(
            re.search(r"<!--\s*gitweave", self.all_runs, re.IGNORECASE)
            or re.search(r"<!-- terraform-plan", self.all_runs, re.IGNORECASE)
            or re.search(r"gitweave.tf.plan", self.all_runs, re.IGNORECASE)
        )
        self.assertTrue(
            has_marker,
            "Comment body has no unique marker. "
            "Embed an HTML comment like '<!-- gitweave-tf-plan -->' in the body "
            "so the update logic can find this comment on subsequent pushes.",
        )

    def test_find_existing_comment_step_searches_by_marker(self):
        """
        A step must search for the existing comment using the marker string,
        typically by calling 'gh api repos/.../issues/.../comments' and
        filtering by the marker text with grep or jq.
        """
        all_runs = self.all_runs
        has_search = bool(
            re.search(r"gh\s+api.*comments", all_runs)
            and (
                re.search(r"gitweave", all_runs, re.IGNORECASE)
                or re.search(r"jq\s+.*body", all_runs)
                or re.search(r"grep\s+.*marker", all_runs, re.IGNORECASE)
            )
        )
        self.assertTrue(
            has_search,
            "No step found that searches for an existing PR comment by marker. "
            "Add a step that lists PR comments via 'gh api .../comments' and "
            "identifies the existing gitweave comment by its marker string.",
        )


class TestCommentUpdateNotDuplicate(unittest.TestCase):
    """
    Subsequent pushes to the same PR must UPDATE the existing comment via
    PATCH, not create a new one via POST. This prevents comment spam.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)
        self.all_runs = _all_run_text_in_job(self.steps)

    def test_comment_step_uses_patch_to_update_existing_comment(self):
        """
        When an existing comment is found, the step must call
        'gh api --method PATCH .../comments/{id}' to update it,
        not create a new one via POST.
        """
        has_patch = bool(re.search(r"--method\s+PATCH", self.all_runs, re.IGNORECASE))
        self.assertTrue(
            has_patch,
            "No 'gh api --method PATCH' found in plan job steps. "
            "The comment update path must use PATCH on the existing comment URL "
            "to avoid duplicating comments on every push.",
        )

    def test_comment_step_uses_post_for_new_comment_when_none_exists(self):
        """
        When no existing comment is found, the step must create a new comment
        via POST to the issues comments endpoint.
        """
        has_post = bool(
            re.search(r"--method\s+POST", self.all_runs, re.IGNORECASE)
            or re.search(r"gh\s+pr\s+comment", self.all_runs)
            or re.search(r"gh\s+api\s+[^-]", self.all_runs)  # default gh api is POST
        )
        self.assertTrue(
            has_post,
            "No step found that creates a NEW comment when none exists. "
            "Add logic to POST a new comment when no existing gitweave comment "
            "is found on the PR.",
        )

    def test_update_logic_branches_on_comment_id(self):
        """
        The step must branch on whether a comment ID was found:
        if comment_id != '' → PATCH to update; else → POST to create.
        This conditional is what prevents duplicate comments.
        """
        all_runs = self.all_runs
        has_branch = bool(
            re.search(r"if\s+\[", all_runs)  # shell if [ $COMMENT_ID ]
            or re.search(r'\$\{\{.*comment_id', all_runs, re.IGNORECASE)
            or re.search(r'if.*comment.*id', all_runs, re.IGNORECASE)
            or re.search(r'\$COMMENT_ID', all_runs)
            or re.search(r'comment_id=', all_runs)
        )
        self.assertTrue(
            has_branch,
            "No conditional branching on comment_id found. "
            "The step must check whether an existing comment ID was found and "
            "branch to PATCH (update) vs POST (create) accordingly.",
        )


class TestCommentTruncation(unittest.TestCase):
    """
    Plan output must be truncated at 65000 characters to stay within GitHub's
    comment body size limit. Truncated output must include a visible indicator.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)
        self.all_runs = _all_run_text_in_job(self.steps)

    def test_plan_output_truncated_at_65000_chars(self):
        """
        The step script must truncate the plan output at 65000 characters.
        Accepts: head -c 65000, ${var:0:65000}, cut -c-65000, or literal '65000'.
        """
        has_truncation = bool(
            re.search(r"65000", self.all_runs)
            or re.search(r"head\s+-c", self.all_runs)
        )
        self.assertTrue(
            has_truncation,
            "No 65000-character truncation found in plan job steps. "
            "Truncate plan output at 65000 chars to prevent hitting GitHub's "
            "comment body limit. Use 'head -c 65000' or '${output:0:65000}'.",
        )

    def test_truncated_output_appends_truncation_notice(self):
        """
        When plan output is truncated, the comment must append
        '\\n...\\n[Output truncated]' so reviewers know the output is incomplete.
        """
        has_truncation_notice = bool(
            re.search(r"Output truncated", self.all_runs, re.IGNORECASE)
            or re.search(r"\[truncated\]", self.all_runs, re.IGNORECASE)
        )
        self.assertTrue(
            has_truncation_notice,
            "No '[Output truncated]' notice found in plan job steps. "
            "When output is truncated, append '\\n...\\n[Output truncated]' "
            "to the comment body so reviewers know the plan is incomplete.",
        )


class TestNoCommentWhenNoChanges(unittest.TestCase):
    """
    If terraform plan exits with code 0 and no infrastructure changes are
    pending, posting a comment adds noise without value. The comment step
    must be skipped in this case.

    Terraform exit codes:
      0 = succeeded, no changes
      1 = error
      2 = succeeded, changes present
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)
        self.all_runs = _all_run_text_in_job(self.steps)

    def test_comment_step_skipped_when_exit_code_is_zero_no_changes(self):
        """
        The comment step must not post when terraform plan exits 0 with no
        changes. Check that the step's 'if' condition or the script logic
        skips posting when exit code == 0 (no changes).

        Terraform plan uses -detailed-exitcode: 0=no changes, 2=changes.
        The comment step must only post when exit code is 2 (changes present)
        or 1 (error), NOT when exit code is 0.
        """
        all_runs = self.all_runs
        # Look for logic that checks exit code before posting
        handles_no_changes = bool(
            re.search(r"exit.?code.*[!=]=.*0", all_runs, re.IGNORECASE)
            or re.search(r"detailed.exitcode", all_runs, re.IGNORECASE)
            or re.search(r"exitcode.*[!=]=.*0", all_runs, re.IGNORECASE)
            or re.search(r"\$\?.*[!=]=.*0", all_runs)
            or re.search(r"TF_EXIT_CODE", all_runs)
        )
        self.assertTrue(
            handles_no_changes,
            "No exit-code check found to suppress comments when there are no changes. "
            "Use 'terraform plan -detailed-exitcode' and capture the exit code. "
            "Only post a comment when exit code is != 0 (1=error, 2=changes present).",
        )

    def test_terraform_plan_uses_detailed_exitcode_flag(self):
        """
        The terraform plan command must include '-detailed-exitcode' so the
        script can distinguish 'no changes' (0) from 'changes present' (2).
        Without this flag, exit 0 is ambiguous.
        """
        has_detailed_exitcode = "-detailed-exitcode" in self.all_runs
        self.assertTrue(
            has_detailed_exitcode,
            "terraform plan step does not use '-detailed-exitcode'. "
            "This flag causes plan to exit 2 when changes are present and 0 "
            "when there are none, enabling the script to skip the comment "
            "when no infrastructure changes exist.",
        )


class TestPlanJobContinuesOnPlanError(unittest.TestCase):
    """
    When terraform plan exits with code 1 (error), the plan step itself will
    fail. The comment step must still run to report the error to the PR author.
    This requires the plan step to use continue-on-error or the comment step
    to use 'if: always()'.
    """

    def setUp(self):
        self.doc = _load_workflow()
        self.steps = _plan_job_steps(self.doc)

    def test_plan_step_uses_continue_on_error_or_comment_uses_always(self):
        """
        Either the terraform plan step must use 'continue-on-error: true'
        OR the PR comment step must have 'if: always()' so the error is
        surfaced to the PR author even when plan fails.
        """
        plan_steps = _find_steps_by_run_pattern(
            self.steps, r"terraform\s+plan"
        )
        plan_continues_on_error = any(
            s.get("continue-on-error") is True for s in plan_steps
        )

        comment_steps = _find_steps_by_run_pattern(
            self.steps, r"gh\s+(api|pr\s+comment)"
        )
        comment_uses_always = any(
            "always()" in str(s.get("if", "") or "") for s in comment_steps
        )

        self.assertTrue(
            plan_continues_on_error or comment_uses_always,
            "Neither the terraform plan step uses 'continue-on-error: true' "
            "nor does the comment step use 'if: always()'. "
            "When plan exits 1 (error), the comment step will be skipped and "
            "the PR author will not see the error in the comment. "
            "Add 'continue-on-error: true' to the plan step or "
            "'if: always() && github.event_name == \"pull_request\"' "
            "to the comment step.",
        )


class TestWorkflowPermissionsNotBroken(unittest.TestCase):
    """
    Adding pull-requests: write must not accidentally relax the permission
    model established for the apply job. Guard rails from
    test_infra_workflow_gates.py must still hold.
    """

    def setUp(self):
        self.doc = _load_workflow()

    def test_apply_job_still_does_not_have_pull_requests_write(self):
        """
        The apply job must NOT receive pull-requests: write — it only needs
        id-token: write and contents: read for cloud deployment. Granting
        extra permissions to apply would violate the least-privilege policy.
        """
        apply_job = _find_job(self.doc, "apply")
        if apply_job is None:
            self.skipTest("apply job not found")
        apply_perms = (apply_job.get("permissions") or {})
        if isinstance(apply_perms, dict):
            pr_perm = apply_perms.get("pull-requests")
            self.assertNotEqual(
                pr_perm,
                "write",
                "apply job has 'pull-requests: write'. This permission is only needed "
                "by the plan job for commenting. Remove it from apply to maintain "
                "least-privilege access on the deployment job.",
            )

    def test_workflow_level_permissions_contents_is_still_read(self):
        """
        The workflow-level contents permission must remain 'read' — adding
        pull-requests: write must not widen contents access.
        """
        workflow_perms = self.doc.get("permissions") or {}
        if isinstance(workflow_perms, dict) and "contents" in workflow_perms:
            self.assertEqual(
                workflow_perms.get("contents"),
                "read",
                f"Workflow-level contents permission changed to "
                f"{workflow_perms.get('contents')!r}. "
                "It must remain 'read' — do not widen access when adding "
                "pull-requests: write.",
            )


if __name__ == "__main__":
    unittest.main()
