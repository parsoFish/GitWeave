"""
Tests for GITHUB_TOKEN scope minimization across all .github/workflows/*.yaml files.

This file verifies that:
  - Every workflow file declares explicit permissions (at top-level or on every job),
    so the repository never relies on the implicit write-all default.
  - Each workflow grants only the scopes it actually needs (least-privilege).
  - A CI check script (scripts/check_workflow_permissions.py) exists and exits non-zero
    when passed a directory that contains a workflow lacking a permissions block.
  - docs/security.md exists and contains a permissions table mapping each workflow to
    its required scopes with justification.

Expected final permissions per workflow
---------------------------------------
  ci.yaml                        : contents: read
  gitweave-apply.yaml            : contents: read, pull-requests: write
  gitweave-infra.yaml            : id-token: write, contents: read, pull-requests: write
  module-update-propagation.yaml : contents: write, pull-requests: write
  module-calver.yaml             : (job-level or top-level) contents: read / contents: write
  overlay-validate.yaml          : contents: read
  tf-validate.yaml               : contents: read

All tests that target missing or incorrect permissions will FAIL until the
implementation is in place (TDD red phase).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest

import yaml

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")
CHECK_SCRIPT = os.path.join(REPO_ROOT, "scripts", "check_workflow_permissions.py")
SECURITY_DOC = os.path.join(REPO_ROOT, "docs", "security.md")


def _load_workflow(name: str) -> dict:
    """Parse a workflow YAML file by basename and return the document dict."""
    path = os.path.join(WORKFLOWS_DIR, name)
    with open(path) as f:
        return yaml.safe_load(f)


def _workflow_has_explicit_permissions(doc: dict) -> bool:
    """
    Return True when a workflow has explicit permissions declared at the
    top level OR on every individual job (either form satisfies the requirement
    that no job can accidentally inherit the write-all default).
    """
    if "permissions" in doc:
        return True
    jobs = doc.get("jobs", {})
    if not jobs:
        return False
    return all("permissions" in job for job in jobs.values())


def _collect_all_permissions(doc: dict) -> dict[str, set[str]]:
    """
    Return a mapping of {scope: set_of_values} describing all permission
    scopes declared anywhere in the workflow (top-level union with per-job).
    This lets tests assert that a required scope exists somewhere without
    prescribing whether it lives at the workflow or job level.
    """
    result: dict[str, set[str]] = {}
    top = doc.get("permissions") or {}
    if isinstance(top, dict):
        for scope, value in top.items():
            result.setdefault(scope, set()).add(value)
    for job in doc.get("jobs", {}).values():
        job_perms = job.get("permissions") or {}
        if isinstance(job_perms, dict):
            for scope, value in job_perms.items():
                result.setdefault(scope, set()).add(value)
    return result


def _scope_has_value(doc: dict, scope: str, expected_value: str) -> bool:
    """Return True when *scope* is set to *expected_value* anywhere in the workflow."""
    all_perms = _collect_all_permissions(doc)
    return expected_value in all_perms.get(scope, set())


def _top_level_permissions(doc: dict) -> dict:
    """Return the top-level permissions mapping (empty dict if absent)."""
    perms = doc.get("permissions")
    if isinstance(perms, dict):
        return perms
    return {}


# ---------------------------------------------------------------------------
# 1. All workflows must have explicit permissions
# ---------------------------------------------------------------------------


class TestAllWorkflowsHaveExplicitPermissions(unittest.TestCase):
    """
    Verify that every workflow in .github/workflows/ declares permissions
    at the top-level or on every job, preventing the implicit write-all default.
    """

    def setUp(self):
        self.workflow_files = sorted(
            f
            for f in os.listdir(WORKFLOWS_DIR)
            if f.endswith((".yaml", ".yml"))
        )

    def test_workflows_directory_contains_yaml_files(self):
        """There must be at least one workflow YAML to validate."""
        self.assertGreater(
            len(self.workflow_files),
            0,
            f"No .yaml files found in {WORKFLOWS_DIR}",
        )

    def test_every_workflow_has_explicit_permissions_block(self):
        """
        Every workflow must declare permissions explicitly.

        A missing permissions block causes GitHub Actions to grant the
        GITHUB_TOKEN write access to all scopes (the 'write-all' default),
        violating the principle of least privilege.
        """
        missing = []
        for filename in self.workflow_files:
            path = os.path.join(WORKFLOWS_DIR, filename)
            with open(path) as f:
                doc = yaml.safe_load(f) or {}
            if not _workflow_has_explicit_permissions(doc):
                missing.append(filename)

        self.assertEqual(
            missing,
            [],
            f"The following workflows are missing explicit permissions blocks "
            f"(they inherit the write-all default): {missing!r}. "
            f"Add a top-level 'permissions:' block or add 'permissions:' to every job.",
        )

    def test_no_workflow_grants_write_all_via_string(self):
        """
        A top-level `permissions: write-all` is as dangerous as no permissions
        block. No workflow should use the string form of write-all.
        """
        offenders = []
        for filename in self.workflow_files:
            path = os.path.join(WORKFLOWS_DIR, filename)
            with open(path) as f:
                doc = yaml.safe_load(f) or {}
            top_perms = doc.get("permissions")
            if isinstance(top_perms, str) and top_perms in ("write-all", "read-all"):
                offenders.append((filename, top_perms))

        self.assertEqual(
            offenders,
            [],
            f"The following workflows use the blanket permissions string "
            f"(write-all / read-all) instead of explicit scope declarations: "
            f"{offenders!r}",
        )


# ---------------------------------------------------------------------------
# 2. Per-workflow permission requirements
# ---------------------------------------------------------------------------


class TestGitweaveApplyPermissions(unittest.TestCase):
    """
    gitweave-apply.yaml must have:
      contents: read    — to check out the repo
      pull-requests: write — to post dry-run summaries as PR comments
    """

    WORKFLOW = "gitweave-apply.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """gitweave-apply.yaml must declare permissions explicitly."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing an explicit permissions block — "
            "the job inherits write-all by default",
        )

    def test_contents_is_read(self):
        """gitweave-apply.yaml needs contents: read to check out the repository."""
        self.assertTrue(
            _scope_has_value(self.doc, "contents", "read"),
            f"{self.WORKFLOW} does not declare 'contents: read' anywhere",
        )

    def test_pull_requests_is_write(self):
        """gitweave-apply.yaml needs pull-requests: write to post PR comments."""
        self.assertTrue(
            _scope_has_value(self.doc, "pull-requests", "write"),
            f"{self.WORKFLOW} does not declare 'pull-requests: write' anywhere",
        )

    def test_does_not_grant_id_token_write(self):
        """
        gitweave-apply.yaml does not use OIDC federation, so id-token: write
        is unnecessary and must not be granted.
        """
        all_perms = _collect_all_permissions(self.doc)
        id_token_values = all_perms.get("id-token", set())
        self.assertNotIn(
            "write",
            id_token_values,
            f"{self.WORKFLOW} grants 'id-token: write' unnecessarily — "
            "this scope is only required for OIDC authentication",
        )

    def test_top_level_permissions_declared(self):
        """
        The permissions block should be at the top level so it applies to all
        jobs and cannot be accidentally omitted from a new job.
        """
        self.assertIn(
            "permissions",
            self.doc,
            f"{self.WORKFLOW} has no top-level 'permissions:' key — "
            "declare permissions at the workflow level so all jobs inherit them",
        )


class TestGitweaveInfraPermissions(unittest.TestCase):
    """
    gitweave-infra.yaml must have:
      id-token: write    — for OIDC authentication in the apply job
      contents: read     — to check out infra/ code
      pull-requests: write — to post the Terraform plan as a PR comment
    """

    WORKFLOW = "gitweave-infra.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """gitweave-infra.yaml must declare permissions explicitly at workflow or job level."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing an explicit permissions block",
        )

    def test_id_token_write_present(self):
        """
        The apply job uses OIDC to authenticate with the cloud provider.
        id-token: write must be declared somewhere in the workflow.
        """
        self.assertTrue(
            _scope_has_value(self.doc, "id-token", "write"),
            f"{self.WORKFLOW} does not declare 'id-token: write' — "
            "the OIDC-based apply job will fail without this scope",
        )

    def test_contents_read_present(self):
        """gitweave-infra.yaml needs contents: read to check out infra/ code."""
        self.assertTrue(
            _scope_has_value(self.doc, "contents", "read"),
            f"{self.WORKFLOW} does not declare 'contents: read' anywhere",
        )

    def test_pull_requests_write_present(self):
        """
        The plan job posts Terraform plan output as a PR comment.
        pull-requests: write must be present.
        """
        self.assertTrue(
            _scope_has_value(self.doc, "pull-requests", "write"),
            f"{self.WORKFLOW} does not declare 'pull-requests: write' anywhere",
        )

    def test_apply_job_has_id_token_write(self):
        """
        The apply job specifically requires id-token: write for OIDC.
        Verify that at least one job in the workflow declares this scope.
        """
        jobs = self.doc.get("jobs", {})
        jobs_with_id_token_write = [
            job_id
            for job_id, job in jobs.items()
            if isinstance(job.get("permissions"), dict)
            and job["permissions"].get("id-token") == "write"
        ]
        self.assertGreater(
            len(jobs_with_id_token_write),
            0,
            f"{self.WORKFLOW} has no job with 'id-token: write' — "
            "the Terraform apply job requires OIDC authentication",
        )

    def test_plan_job_has_pull_requests_write(self):
        """
        The plan job posts PR comments, so it needs pull-requests: write
        either via job-level permissions or inherited from the top level.
        """
        jobs = self.doc.get("jobs", {})
        plan_jobs = {
            job_id: job
            for job_id, job in jobs.items()
            if "plan" in job_id.lower()
        }
        self.assertGreater(
            len(plan_jobs),
            0,
            f"{self.WORKFLOW} has no job with 'plan' in its id — cannot verify plan job permissions",
        )
        for job_id, job in plan_jobs.items():
            job_perms = job.get("permissions") or {}
            top_perms = _top_level_permissions(self.doc)
            effective_pr_perm = job_perms.get("pull-requests") or top_perms.get("pull-requests")
            self.assertEqual(
                effective_pr_perm,
                "write",
                f"Plan job '{job_id}' does not have effective 'pull-requests: write' — "
                "it cannot post PR comments without this permission",
            )


class TestCIWorkflowMinimalPermissions(unittest.TestCase):
    """
    ci.yaml is a read-only linting and testing workflow.
    It must declare contents: read and must not grant any write permissions.
    """

    WORKFLOW = "ci.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_top_level_permissions_block(self):
        """ci.yaml must have a top-level permissions block."""
        self.assertIn(
            "permissions",
            self.doc,
            f"{self.WORKFLOW} is missing a top-level 'permissions:' block",
        )

    def test_contents_is_read(self):
        """ci.yaml only reads the repository; contents must be 'read'."""
        perms = _top_level_permissions(self.doc)
        self.assertEqual(
            perms.get("contents"),
            "read",
            f"{self.WORKFLOW} top-level permissions.contents is "
            f"{perms.get('contents')!r}, expected 'read'",
        )

    def test_no_write_permissions_granted(self):
        """
        ci.yaml is a pure read/test workflow. No scope should be 'write'.
        Granting write access here expands blast radius unnecessarily.
        """
        all_perms = _collect_all_permissions(self.doc)
        write_scopes = {scope: vals for scope, vals in all_perms.items() if "write" in vals}
        self.assertEqual(
            write_scopes,
            {},
            f"{self.WORKFLOW} grants write permissions unnecessarily: {write_scopes!r}",
        )

    def test_no_id_token_write_granted(self):
        """ci.yaml does not use OIDC; id-token: write must not be present."""
        all_perms = _collect_all_permissions(self.doc)
        self.assertNotIn(
            "write",
            all_perms.get("id-token", set()),
            f"{self.WORKFLOW} grants 'id-token: write' — not required for a CI lint/test job",
        )


class TestModuleUpdatePropagationPermissions(unittest.TestCase):
    """
    module-update-propagation.yaml must have:
      contents: write     — to push update branches to consumer repos
      pull-requests: write — to open PRs in consumer repos
    """

    WORKFLOW = "module-update-propagation.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """module-update-propagation.yaml must declare permissions explicitly."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing an explicit permissions block",
        )

    def test_contents_is_write(self):
        """
        The propagation job clones consumer repos and pushes update branches.
        contents: write is required for git push operations via GITHUB_TOKEN.
        """
        self.assertTrue(
            _scope_has_value(self.doc, "contents", "write"),
            f"{self.WORKFLOW} does not declare 'contents: write' — "
            "the job cannot push branches without this scope",
        )

    def test_pull_requests_is_write(self):
        """The propagation job opens PRs in consumer repos via gh pr create."""
        self.assertTrue(
            _scope_has_value(self.doc, "pull-requests", "write"),
            f"{self.WORKFLOW} does not declare 'pull-requests: write' — "
            "the job cannot open PRs without this scope",
        )


class TestModuleCalverPermissions(unittest.TestCase):
    """
    module-calver.yaml has two jobs with different needs:
      validate-version job: contents: read  (just reads and diffs)
      tag-version job:      contents: write (pushes tags)
    Both must have explicit job-level permissions.
    """

    WORKFLOW = "module-calver.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """module-calver.yaml must declare permissions at workflow or all-job level."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing explicit permissions — "
            "add permissions to every job or a top-level block",
        )

    def test_validate_version_job_has_contents_read(self):
        """The validate-version job only reads the repo; contents: read is sufficient."""
        jobs = self.doc.get("jobs", {})
        validate_job = None
        for job_id, job in jobs.items():
            if "validate" in job_id.lower():
                validate_job = job
                break
        self.assertIsNotNone(
            validate_job,
            f"{self.WORKFLOW} has no job with 'validate' in its id",
        )
        job_perms = validate_job.get("permissions") or {}
        top_perms = _top_level_permissions(self.doc)
        effective = job_perms.get("contents") or top_perms.get("contents")
        self.assertEqual(
            effective,
            "read",
            f"validate-version job effective contents permission is {effective!r}, expected 'read'",
        )

    def test_tag_version_job_has_contents_write(self):
        """The tag-version job pushes CalVer tags; contents: write is required."""
        jobs = self.doc.get("jobs", {})
        tag_job = None
        for job_id, job in jobs.items():
            if "tag" in job_id.lower():
                tag_job = job
                break
        self.assertIsNotNone(
            tag_job,
            f"{self.WORKFLOW} has no job with 'tag' in its id",
        )
        job_perms = tag_job.get("permissions") or {}
        self.assertEqual(
            job_perms.get("contents"),
            "write",
            f"tag-version job permissions.contents is {job_perms.get('contents')!r}, expected 'write'",
        )


class TestOverlayValidatePermissions(unittest.TestCase):
    """overlay-validate.yaml is a pure validation workflow — contents: read only."""

    WORKFLOW = "overlay-validate.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """overlay-validate.yaml must declare permissions explicitly."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing explicit permissions",
        )

    def test_contents_is_read(self):
        """overlay-validate.yaml only reads config files; contents must be 'read'."""
        top_perms = _top_level_permissions(self.doc)
        self.assertEqual(
            top_perms.get("contents"),
            "read",
            f"{self.WORKFLOW} top-level contents permission is "
            f"{top_perms.get('contents')!r}, expected 'read'",
        )

    def test_no_write_permissions_granted(self):
        """overlay-validate.yaml is read-only; no write scopes should be present."""
        all_perms = _collect_all_permissions(self.doc)
        write_scopes = {scope: vals for scope, vals in all_perms.items() if "write" in vals}
        self.assertEqual(
            write_scopes,
            {},
            f"{self.WORKFLOW} grants write permissions unnecessarily: {write_scopes!r}",
        )


class TestTfValidatePermissions(unittest.TestCase):
    """tf-validate.yaml runs terraform validate on PRs — contents: read only."""

    WORKFLOW = "tf-validate.yaml"

    def setUp(self):
        self.doc = _load_workflow(self.WORKFLOW)

    def test_has_explicit_permissions_block(self):
        """tf-validate.yaml must declare permissions explicitly."""
        self.assertTrue(
            _workflow_has_explicit_permissions(self.doc),
            f"{self.WORKFLOW} is missing explicit permissions",
        )

    def test_contents_is_read(self):
        """tf-validate.yaml only reads infra/ code; contents must be 'read'."""
        top_perms = _top_level_permissions(self.doc)
        self.assertEqual(
            top_perms.get("contents"),
            "read",
            f"{self.WORKFLOW} top-level contents permission is "
            f"{top_perms.get('contents')!r}, expected 'read'",
        )

    def test_no_write_permissions_granted(self):
        """tf-validate.yaml is read-only; no write scopes should be present."""
        all_perms = _collect_all_permissions(self.doc)
        write_scopes = {scope: vals for scope, vals in all_perms.items() if "write" in vals}
        self.assertEqual(
            write_scopes,
            {},
            f"{self.WORKFLOW} grants write permissions unnecessarily: {write_scopes!r}",
        )


# ---------------------------------------------------------------------------
# 3. CI check script: scripts/check_workflow_permissions.py
# ---------------------------------------------------------------------------


class TestCIPermissionsCheckScriptExists(unittest.TestCase):
    """The CI check script must exist so it can be called from ci.yaml."""

    def test_check_script_file_exists(self):
        """scripts/check_workflow_permissions.py must be present in the repository."""
        self.assertTrue(
            os.path.isfile(CHECK_SCRIPT),
            f"CI check script not found at {CHECK_SCRIPT} — "
            "create scripts/check_workflow_permissions.py to enforce permissions presence",
        )

    def test_check_script_is_executable_python(self):
        """The script must be valid Python (importable syntax)."""
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by test_check_script_file_exists")
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", CHECK_SCRIPT],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"scripts/check_workflow_permissions.py has syntax errors:\n{result.stderr}",
        )


class TestCIPermissionsCheckScriptBehavior(unittest.TestCase):
    """
    Verify the observable behaviour of the permissions check script without
    relying on its implementation details.

    The script must:
      - Exit 0 when every workflow in a directory has a permissions block.
      - Exit non-zero when any workflow lacks a permissions block.
      - Print the offending filename to stderr or stdout when it fails.
    """

    def _run_script(self, workflows_dir: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, CHECK_SCRIPT, workflows_dir],
            capture_output=True,
            text=True,
        )

    def _write_tmp_workflow(self, tmp_dir: str, name: str, content: str) -> None:
        path = os.path.join(tmp_dir, name)
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))

    def test_exits_zero_when_all_workflows_have_permissions(self):
        """Script exits 0 when every workflow file has an explicit permissions block."""
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_tmp_workflow(
                tmp_dir,
                "good.yaml",
                """\
                name: Good Workflow
                'on': push
                permissions:
                  contents: read
                jobs:
                  build:
                    runs-on: ubuntu-latest
                    steps:
                      - uses: actions/checkout@v4
                """,
            )
            result = self._run_script(tmp_dir)
            self.assertEqual(
                result.returncode,
                0,
                f"Script exited {result.returncode} for a valid workflow.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_exits_nonzero_when_workflow_missing_permissions(self):
        """Script exits non-zero when a workflow has no permissions block."""
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_tmp_workflow(
                tmp_dir,
                "missing_perms.yaml",
                """\
                name: Bad Workflow
                'on': push
                jobs:
                  build:
                    runs-on: ubuntu-latest
                    steps:
                      - uses: actions/checkout@v4
                """,
            )
            result = self._run_script(tmp_dir)
            self.assertNotEqual(
                result.returncode,
                0,
                "Script should exit non-zero when a workflow lacks permissions, "
                f"but it exited 0.\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_reports_offending_filename_on_failure(self):
        """Script must name the offending workflow file in its output so it is actionable."""
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_tmp_workflow(
                tmp_dir,
                "offender.yaml",
                """\
                name: Missing Perms
                'on': push
                jobs:
                  build:
                    runs-on: ubuntu-latest
                    steps:
                      - uses: actions/checkout@v4
                """,
            )
            result = self._run_script(tmp_dir)
            combined_output = result.stdout + result.stderr
            self.assertIn(
                "offender.yaml",
                combined_output,
                "Script output does not name the offending file 'offender.yaml' — "
                "developers need to know which workflow to fix.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_handles_empty_directory_gracefully(self):
        """Script must exit 0 (or with a clear message) when the directory has no YAML files."""
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self._run_script(tmp_dir)
            # Exit 0 is acceptable for an empty directory — nothing to check.
            # Exit non-zero is also acceptable if the script treats an empty dir
            # as a configuration error (no workflows defined).
            # What is NOT acceptable is an unhandled exception (traceback).
            self.assertNotIn(
                "Traceback",
                result.stderr,
                f"Script raised an unhandled exception on empty directory:\n{result.stderr}",
            )

    def test_exits_zero_when_all_jobs_have_job_level_permissions(self):
        """
        A workflow with no top-level permissions but with permissions on every
        job is still compliant — the script must accept this form.
        """
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_tmp_workflow(
                tmp_dir,
                "job_level_perms.yaml",
                """\
                name: Job Level Perms
                'on': push
                jobs:
                  build:
                    runs-on: ubuntu-latest
                    permissions:
                      contents: read
                    steps:
                      - uses: actions/checkout@v4
                  test:
                    runs-on: ubuntu-latest
                    permissions:
                      contents: read
                    steps:
                      - run: echo test
                """,
            )
            result = self._run_script(tmp_dir)
            self.assertEqual(
                result.returncode,
                0,
                "Script should accept a workflow where every job has permissions, "
                f"but it exited {result.returncode}.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_exits_nonzero_when_only_some_jobs_have_permissions(self):
        """
        When some jobs have permissions and some do not, the workflow is still
        non-compliant — jobs without permissions inherit the top-level default.
        """
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_tmp_workflow(
                tmp_dir,
                "partial_perms.yaml",
                """\
                name: Partial Perms
                'on': push
                jobs:
                  build:
                    runs-on: ubuntu-latest
                    permissions:
                      contents: read
                    steps:
                      - uses: actions/checkout@v4
                  deploy:
                    runs-on: ubuntu-latest
                    steps:
                      - run: echo deploy
                """,
            )
            result = self._run_script(tmp_dir)
            self.assertNotEqual(
                result.returncode,
                0,
                "Script should reject a workflow where only SOME jobs have permissions, "
                f"but it exited 0.\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )

    def test_passes_against_real_workflows_directory_when_fully_implemented(self):
        """
        When all workflow files have been updated, the script must exit 0 against
        the real .github/workflows/ directory.  This acts as the integration gate.
        """
        if not os.path.isfile(CHECK_SCRIPT):
            self.skipTest("Script not present — covered by TestCIPermissionsCheckScriptExists")
        result = self._run_script(WORKFLOWS_DIR)
        self.assertEqual(
            result.returncode,
            0,
            "The permissions check script found violations in the real workflow directory.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}\n\n"
            "Fix the listed workflows by adding explicit 'permissions:' blocks.",
        )


# ---------------------------------------------------------------------------
# 4. CI workflow must invoke the permissions check script
# ---------------------------------------------------------------------------


class TestCIWorkflowInvokesPermissionsCheck(unittest.TestCase):
    """
    The CI workflow (ci.yaml) must include a step that runs the permissions
    check script so it becomes an automated gate on every PR.
    """

    def setUp(self):
        self.doc = _load_workflow("ci.yaml")

    def _all_steps(self) -> list:
        steps = []
        for job in self.doc.get("jobs", {}).values():
            steps.extend(job.get("steps", []))
        return steps

    def test_ci_workflow_has_permissions_check_step(self):
        """
        ci.yaml must include a step that invokes check_workflow_permissions.py
        (or an equivalent permissions audit command) to gate PRs automatically.
        """
        steps = self._all_steps()
        perms_check_steps = [
            s
            for s in steps
            if "check_workflow_permissions" in str(s.get("run", ""))
            or "check_workflow_permissions" in str(s.get("uses", ""))
        ]
        self.assertGreater(
            len(perms_check_steps),
            0,
            "ci.yaml has no step invoking 'check_workflow_permissions' — "
            "add a step to run scripts/check_workflow_permissions.py as a PR gate",
        )

    def test_permissions_check_step_does_not_continue_on_error(self):
        """
        The permissions check step must NOT set continue-on-error: true.
        A missing permissions block must block the PR.
        """
        steps = self._all_steps()
        perms_check_steps = [
            s
            for s in steps
            if "check_workflow_permissions" in str(s.get("run", ""))
        ]
        for step in perms_check_steps:
            self.assertNotEqual(
                step.get("continue-on-error"),
                True,
                f"Permissions check step '{step.get('name', '<unnamed>')}' has "
                "continue-on-error: true — permission violations must fail the job",
            )


# ---------------------------------------------------------------------------
# 5. Security documentation
# ---------------------------------------------------------------------------


class TestSecurityDocumentationExists(unittest.TestCase):
    """
    docs/security.md must exist and contain a permissions table that maps
    each workflow to its required scopes and justification.
    """

    def test_security_md_exists(self):
        """docs/security.md must be present in the repository."""
        self.assertTrue(
            os.path.isfile(SECURITY_DOC),
            f"docs/security.md not found at {SECURITY_DOC} — "
            "create this file with the permissions table per the acceptance criteria",
        )

    def test_security_md_contains_permissions_heading(self):
        """docs/security.md must contain a 'Permissions' or 'permissions' heading."""
        if not os.path.isfile(SECURITY_DOC):
            self.skipTest("docs/security.md not present — covered by test_security_md_exists")
        with open(SECURITY_DOC) as f:
            content = f.read()
        self.assertRegex(
            content,
            r"(?i)#+\s*.*permission",
            "docs/security.md does not contain a heading with 'permission' — "
            "add a permissions table section",
        )

    def test_security_md_mentions_all_workflows(self):
        """docs/security.md must reference every workflow in .github/workflows/."""
        if not os.path.isfile(SECURITY_DOC):
            self.skipTest("docs/security.md not present — covered by test_security_md_exists")
        with open(SECURITY_DOC) as f:
            content = f.read()
        workflow_names = [
            os.path.splitext(f)[0]
            for f in os.listdir(WORKFLOWS_DIR)
            if f.endswith((".yaml", ".yml"))
        ]
        missing_refs = [name for name in workflow_names if name not in content]
        self.assertEqual(
            missing_refs,
            [],
            f"docs/security.md does not mention these workflow(s): {missing_refs!r} — "
            "every workflow must appear in the permissions table",
        )

    def test_security_md_contains_markdown_table(self):
        """docs/security.md must contain a Markdown table (pipe-delimited rows)."""
        if not os.path.isfile(SECURITY_DOC):
            self.skipTest("docs/security.md not present — covered by test_security_md_exists")
        with open(SECURITY_DOC) as f:
            content = f.read()
        # A markdown table row looks like: | col | col | col |
        table_rows = [line for line in content.splitlines() if line.strip().startswith("|")]
        self.assertGreater(
            len(table_rows),
            1,
            "docs/security.md does not appear to contain a Markdown table "
            "(expected pipe-delimited rows) — add a permissions table",
        )

    def test_security_md_table_includes_justification_column(self):
        """The permissions table must include a justification/rationale column."""
        if not os.path.isfile(SECURITY_DOC):
            self.skipTest("docs/security.md not present — covered by test_security_md_exists")
        with open(SECURITY_DOC) as f:
            content = f.read()
        self.assertRegex(
            content,
            r"(?i)justif|rationale|reason|why",
            "docs/security.md permissions table should include a justification column "
            "explaining why each scope is required",
        )


if __name__ == "__main__":
    unittest.main()
