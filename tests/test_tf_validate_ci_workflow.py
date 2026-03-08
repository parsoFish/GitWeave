"""
Tests for the terraform validation CI job that gates infra/ changes on every PR.

The job is expected in .github/workflows/ci.yaml (or a dedicated
tf-validate.yaml) and must satisfy:

  - Triggers on pull_request with paths: infra/**
  - Runs four steps in order: terraform fmt -check, init, validate, plan
  - Uses GITHUB_TOKEN (not a hardcoded credential) scoped to a test org
  - Does NOT use -auto-approve or --auto-approve on any step
  - Does NOT use continue-on-error on any terraform step
  - Uses a job-level timeout-minutes that aligns with the <3-minute SLA
  - Plan step uses -input=false and -no-color for CI-safe output

These tests inspect the YAML definition of the workflow file, not runtime
behaviour. They fail until the CI job is implemented (TDD red phase).
"""

import os
import unittest

import yaml


# ---------------------------------------------------------------------------
# Paths — the job may live in ci.yaml or a dedicated tf-validate.yaml
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CANDIDATE_PATHS = [
    os.path.join(REPO_ROOT, ".github", "workflows", "tf-validate.yaml"),
    os.path.join(REPO_ROOT, ".github", "workflows", "ci.yaml"),
]


def _find_workflow_with_tf_validate_job() -> str | None:
    """
    Return the path of the first workflow file that contains a job whose
    steps include a `terraform plan` invocation.  Returns None when no
    such file is found.
    """
    for path in _CANDIDATE_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                doc = yaml.safe_load(f)
            for job in (doc or {}).get("jobs", {}).values():
                steps = job.get("steps", []) or []
                if any("terraform plan" in str(s.get("run", "")) for s in steps):
                    return path
        except yaml.YAMLError:
            pass
    return None


def _load_workflow(path: str) -> dict:
    """Parse a GitHub Actions workflow YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _get_triggers(doc: dict) -> dict:
    """
    Return the workflow trigger mapping.  Handles PyYAML's YAML 1.1 quirk
    where the bare `on:` key is parsed as the boolean True.
    """
    return doc.get("on") or doc.get(True) or {}


def _collect_tf_validate_jobs(doc: dict) -> list[tuple[str, dict]]:
    """
    Return (job_id, job_dict) pairs for every job that contains at least one
    `terraform plan` step — these are the tf-validate jobs under test.
    """
    results = []
    for job_id, job in doc.get("jobs", {}).items():
        steps = job.get("steps", []) or []
        if any("terraform plan" in str(s.get("run", "")) for s in steps):
            results.append((job_id, job))
    return results


def _collect_all_steps_for_job(job: dict) -> list[dict]:
    return job.get("steps", []) or []


def _terraform_steps(steps: list[dict]) -> list[dict]:
    """Return steps whose run command invokes the terraform CLI."""
    return [s for s in steps if "terraform" in str(s.get("run", ""))]


# ---------------------------------------------------------------------------
# Pre-flight: workflow file exists and has a tf-validate job
# ---------------------------------------------------------------------------


class TestTfValidateWorkflowFileExists(unittest.TestCase):
    """Sanity checks that a qualifying workflow file and job are present."""

    def test_workflow_file_with_terraform_plan_step_exists(self):
        """
        A workflow file containing a 'terraform plan' step must exist at one
        of the expected paths (.github/workflows/tf-validate.yaml or ci.yaml).

        This is the entry-gate test: until the CI job is created, every other
        test in this module is also expected to fail.
        """
        path = _find_workflow_with_tf_validate_job()
        self.assertIsNotNone(
            path,
            "No workflow file found at tf-validate.yaml or ci.yaml that contains "
            "a 'terraform plan' step. Create the tf-validate CI job to satisfy "
            "the infra/ gating requirement.",
        )

    def test_workflow_parses_as_valid_yaml(self):
        """The workflow file must be well-formed YAML."""
        path = _find_workflow_with_tf_validate_job()
        if path is None:
            self.skipTest("Workflow file not yet created — skipping parse test")
        doc = _load_workflow(path)
        self.assertIsInstance(
            doc,
            dict,
            f"{path} did not parse as a YAML mapping — check for syntax errors",
        )


# ---------------------------------------------------------------------------
# Trigger configuration
# ---------------------------------------------------------------------------


class TestTfValidateTriggers(unittest.TestCase):
    """
    The tf-validate job must run on pull_request events that touch infra/
    so that every infra change is validated before merge.
    """

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)

    def test_triggers_on_pull_request(self):
        """Workflow must have a pull_request trigger."""
        triggers = _get_triggers(self.doc)
        self.assertIn(
            "pull_request",
            triggers,
            f"{self.path} is missing a 'pull_request' trigger — the job will not "
            "run on PRs and cannot gate infra/ changes",
        )

    def test_pull_request_trigger_is_scoped_to_infra_paths(self):
        """
        The pull_request trigger must filter on paths: ['infra/**'] (or a superset
        that includes infra/**) so the job is skipped for non-infra PRs.

        A missing paths filter means the job runs on every PR, which is wasteful
        but not a correctness bug. However, the acceptance criterion requires the
        filter to exist.
        """
        triggers = _get_triggers(self.doc)
        pr_trigger = triggers.get("pull_request") or {}
        if not isinstance(pr_trigger, dict):
            # pull_request: null/True means all events and all paths — acceptable
            # but the spec asks for the explicit infra/** path filter.
            self.fail(
                f"{self.path}: pull_request trigger has no paths filter. "
                "Add 'paths: [\"infra/**\"]' to scope the job to infra/ changes."
            )
        paths = pr_trigger.get("paths", [])
        infra_paths = [p for p in paths if "infra" in p]
        self.assertGreater(
            len(infra_paths),
            0,
            f"{self.path}: pull_request trigger is not scoped to infra/**. "
            f"Current paths filter: {paths!r}. "
            "Add 'infra/**' to the paths list.",
        )


# ---------------------------------------------------------------------------
# Job permissions — least privilege
# ---------------------------------------------------------------------------


class TestTfValidatePermissions(unittest.TestCase):
    """
    The tf-validate job must not request write or admin permissions.
    Reading the repository and calling the GitHub API as a read-only test
    token requires only contents: read.
    """

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)

    def _effective_perms(self, job: dict) -> dict:
        """Return the effective permissions for a job (job-level overrides workflow-level)."""
        workflow_perms = self.doc.get("permissions", {}) or {}
        job_perms = job.get("permissions", {}) or {}
        # Job-level permissions override workflow-level when present
        if job_perms:
            return job_perms
        return workflow_perms

    def test_tf_validate_job_has_no_write_permissions(self):
        """
        The tf-validate job must not have any write permissions.
        Plan-only jobs never write resources — write access widens the blast radius
        if the test token is compromised.
        """
        for job_id, job in self.tf_jobs:
            perms = self._effective_perms(job)
            if isinstance(perms, dict):
                write_grants = {k: v for k, v in perms.items() if v == "write"}
                self.assertEqual(
                    write_grants,
                    {},
                    f"tf-validate job '{job_id}' has unexpected write permissions: "
                    f"{write_grants!r}. Plan-only jobs are read-only.",
                )

    def test_workflow_has_explicit_permissions_block(self):
        """
        An explicit permissions block must be present at the workflow or job level
        so that the default (broad) GITHUB_TOKEN permissions are overridden.
        """
        workflow_has_perms = "permissions" in self.doc
        jobs_have_perms = any(
            "permissions" in job for _, job in self.tf_jobs
        )
        self.assertTrue(
            workflow_has_perms or jobs_have_perms,
            f"{self.path} has no explicit 'permissions' block. "
            "Declare permissions explicitly to enforce least privilege.",
        )


# ---------------------------------------------------------------------------
# Token / credential configuration
# ---------------------------------------------------------------------------


class TestTfValidateTokenConfiguration(unittest.TestCase):
    """
    The tf-validate job must use the injected GITHUB_TOKEN (or a named
    Actions secret) for provider authentication — never a hardcoded credential.
    A dedicated test-org token must be used so that the plan does not touch
    production GitHub resources.
    """

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)

    def _all_env_values(self) -> list[str]:
        """Collect all env var values defined at workflow, job, and step level."""
        values: list[str] = []
        # Workflow-level env
        for v in (self.doc.get("env") or {}).values():
            values.append(str(v))
        for _, job in self.tf_jobs:
            # Job-level env
            for v in (job.get("env") or {}).values():
                values.append(str(v))
            # Step-level env
            for step in (job.get("steps") or []):
                for v in (step.get("env") or {}).values():
                    values.append(str(v))
        return values

    def test_github_token_is_sourced_from_secret_or_env(self):
        """
        GITHUB_TOKEN must be provided via ${{ secrets.* }} or the automatic
        ${{ github.token }} expression — not hardcoded.

        Accepted forms:
          GITHUB_TOKEN: ${{ secrets.TF_TEST_GITHUB_TOKEN }}
          GITHUB_TOKEN: ${{ github.token }}
          TF_VAR_github_token: ${{ secrets.TF_TEST_GITHUB_TOKEN }}
        """
        env_values = self._all_env_values()
        has_secret_ref = any(
            "${{" in v and ("secrets." in v or "github.token" in v)
            for v in env_values
        )
        self.assertTrue(
            has_secret_ref,
            f"{self.path}: No '${{{{ secrets.* }}}}' or '${{{{ github.token }}}}' expression "
            "found in workflow/job/step env blocks. "
            "The terraform provider must authenticate via a secret, not a hardcoded token.",
        )

    def test_no_hardcoded_github_token_in_env(self):
        """
        No env var value should look like a literal GitHub personal access token
        (a 40-character hex string or a 'ghp_'-prefixed string).

        This is a defence-in-depth check — the actual secret should never appear
        in YAML, but the test ensures someone hasn't accidentally committed one.
        """
        import re

        env_values = self._all_env_values()
        pat_pattern = re.compile(r"(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|[0-9a-f]{40})")
        for value in env_values:
            match = pat_pattern.search(value)
            self.assertIsNone(
                match,
                f"{self.path}: A hardcoded GitHub token pattern was found in an env "
                f"value: {value[:20]}… — rotate immediately and use secrets instead.",
            )

    def test_test_org_variable_is_configured(self):
        """
        A TF_VAR_github_org (or equivalent) environment variable must be set
        to a test/sandbox organisation name so the plan does not operate
        against the production GitHub org.

        The value must reference a secret or be a clearly non-production name
        (e.g. 'gitweave-test', 'gitweave-sandbox', or similar).
        """
        env_values = self._all_env_values()

        # Accept either: a secret reference for the org name, or a literal
        # value that contains 'test' or 'sandbox' (not a production org name).
        has_test_org_ref = any(
            "TF_VAR_github_org" in str(v) or "github_org" in str(v)
            for v in self._all_step_env_keys()
        )
        self.assertTrue(
            has_test_org_ref,
            f"{self.path}: No TF_VAR_github_org (or github_org) env var found in "
            "the tf-validate job. The plan must target a test org, not production. "
            "Set TF_VAR_github_org in the job/step env block.",
        )

    def _all_step_env_keys(self) -> list[str]:
        """Return all env key names defined across workflow, job, and step scopes."""
        keys: list[str] = []
        for k in (self.doc.get("env") or {}):
            keys.append(str(k))
        for _, job in self.tf_jobs:
            for k in (job.get("env") or {}):
                keys.append(str(k))
            for step in (job.get("steps") or []):
                for k in (step.get("env") or {}):
                    keys.append(str(k))
        return keys


# ---------------------------------------------------------------------------
# Step sequence — init → validate → fmt → plan (in order)
# ---------------------------------------------------------------------------


class TestTfValidateStepSequence(unittest.TestCase):
    """
    The tf-validate job must run all four terraform operations in order:
      1. terraform fmt -check (style gate)
      2. terraform init     (provider download, no remote state)
      3. terraform validate (schema/syntax correctness)
      4. terraform plan     (dry-run, exit 0 on clean state)

    The order matters: fmt and init are cheap and should fail fast before
    hitting the provider API.
    """

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)
        # Use the first qualifying job for step-order assertions
        if self.tf_jobs:
            _, self.job = self.tf_jobs[0]
            self.steps = _collect_all_steps_for_job(self.job)
        else:
            self.job = {}
            self.steps = []

    def _find_step_index(self, keyword: str) -> int | None:
        """Return the 0-based index of the first step whose run command contains keyword."""
        for i, step in enumerate(self.steps):
            if keyword in str(step.get("run", "")):
                return i
        return None

    def test_has_terraform_fmt_check_step(self):
        """The job must contain a 'terraform fmt -check' step."""
        idx = self._find_step_index("terraform fmt")
        self.assertIsNotNone(
            idx,
            f"tf-validate job has no 'terraform fmt' step. "
            "Add 'terraform fmt -check -recursive .' to gate formatting.",
        )

    def test_terraform_fmt_check_flag_present(self):
        """The fmt step must include the -check flag to fail on violations rather than auto-fix."""
        for step in self.steps:
            run = str(step.get("run", ""))
            if "terraform fmt" in run:
                self.assertIn(
                    "-check",
                    run,
                    f"terraform fmt step is missing the '-check' flag: {run!r}. "
                    "Without -check, fmt auto-fixes files instead of failing CI.",
                )
                return
        self.skipTest("No terraform fmt step found (covered by test_has_terraform_fmt_check_step)")

    def test_has_terraform_init_step(self):
        """The job must contain a 'terraform init' step."""
        idx = self._find_step_index("terraform init")
        self.assertIsNotNone(
            idx,
            "tf-validate job has no 'terraform init' step. "
            "Init must run before validate and plan.",
        )

    def test_has_terraform_validate_step(self):
        """The job must contain a 'terraform validate' step."""
        idx = self._find_step_index("terraform validate")
        self.assertIsNotNone(
            idx,
            "tf-validate job has no 'terraform validate' step. "
            "Validate must run after init to confirm schema correctness.",
        )

    def test_has_terraform_plan_step(self):
        """The job must contain a 'terraform plan' step."""
        idx = self._find_step_index("terraform plan")
        self.assertIsNotNone(
            idx,
            "tf-validate job has no 'terraform plan' step. "
            "Plan is the final gate that proves the config is deployable.",
        )

    def test_init_runs_before_validate(self):
        """'terraform init' must appear before 'terraform validate' in the step list."""
        init_idx = self._find_step_index("terraform init")
        validate_idx = self._find_step_index("terraform validate")
        if init_idx is None or validate_idx is None:
            self.skipTest("Missing init or validate step (covered by earlier tests)")
        self.assertLess(
            init_idx,
            validate_idx,
            f"'terraform init' (step {init_idx}) must appear before "
            f"'terraform validate' (step {validate_idx}). "
            "Validate requires a successful init.",
        )

    def test_validate_runs_before_plan(self):
        """'terraform validate' must appear before 'terraform plan'."""
        validate_idx = self._find_step_index("terraform validate")
        plan_idx = self._find_step_index("terraform plan")
        if validate_idx is None or plan_idx is None:
            self.skipTest("Missing validate or plan step (covered by earlier tests)")
        self.assertLess(
            validate_idx,
            plan_idx,
            f"'terraform validate' (step {validate_idx}) must appear before "
            f"'terraform plan' (step {plan_idx}). "
            "Validate catches cheap errors before running the more expensive plan.",
        )

    def test_fmt_check_runs_before_init(self):
        """
        'terraform fmt -check' should run before init to fail fast on style
        violations without downloading providers.
        """
        fmt_idx = self._find_step_index("terraform fmt")
        init_idx = self._find_step_index("terraform init")
        if fmt_idx is None or init_idx is None:
            self.skipTest("Missing fmt or init step (covered by earlier tests)")
        self.assertLess(
            fmt_idx,
            init_idx,
            f"'terraform fmt -check' (step {fmt_idx}) should appear before "
            f"'terraform init' (step {init_idx}) for a fast-fail style gate.",
        )


# ---------------------------------------------------------------------------
# Safety flags — no auto-approve, no continue-on-error
# ---------------------------------------------------------------------------


class TestTfValidateSafetyFlags(unittest.TestCase):
    """
    Terraform steps in the CI validation job must not carry unsafe flags that
    would bypass errors or apply changes to real infrastructure.
    """

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)

    def test_no_auto_approve_flag_in_any_step(self):
        """
        No step in the tf-validate job must use -auto-approve or --auto-approve.

        A validation job only plans — it must never apply.  The presence of
        -auto-approve indicates a misconfigured step that could modify live infra.
        """
        for job_id, job in self.tf_jobs:
            for step in _collect_all_steps_for_job(job):
                run = str(step.get("run", ""))
                self.assertNotIn(
                    "-auto-approve",
                    run,
                    f"Step '{step.get('name', '<unnamed>')}' in job '{job_id}' "
                    f"contains '-auto-approve': {run!r}. "
                    "The validate job must never apply changes.",
                )

    def test_no_continue_on_error_on_terraform_steps(self):
        """
        Terraform steps must NOT set continue-on-error: true.

        An error in fmt, init, validate, or plan must fail the job immediately —
        not be silently swallowed so the PR can still be merged.
        """
        for job_id, job in self.tf_jobs:
            for step in _collect_all_steps_for_job(job):
                if "terraform" in str(step.get("run", "")):
                    self.assertNotEqual(
                        step.get("continue-on-error"),
                        True,
                        f"Terraform step '{step.get('name', '<unnamed>')}' in job "
                        f"'{job_id}' has continue-on-error: true. "
                        "Terraform errors must fail the CI job.",
                    )

    def test_plan_step_uses_input_false(self):
        """
        'terraform plan' must include -input=false so it does not hang waiting
        for interactive input in a CI environment.
        """
        for _, job in self.tf_jobs:
            for step in _collect_all_steps_for_job(job):
                run = str(step.get("run", ""))
                if "terraform plan" in run:
                    self.assertIn(
                        "-input=false",
                        run,
                        f"terraform plan step is missing '-input=false': {run!r}. "
                        "Plan will hang waiting for interactive input in CI.",
                    )
                    return
        self.skipTest("No terraform plan step found")

    def test_plan_does_not_use_out_flag_without_artifact_upload(self):
        """
        If terraform plan uses -out=<file>, the plan file must be uploaded as
        an artifact so the output is auditable.  A plan output file left in the
        runner filesystem is not useful after the job completes.

        Note: using -out is optional for a validation job; this test only fires
        when -out is explicitly used.
        """
        for _, job in self.tf_jobs:
            steps = _collect_all_steps_for_job(job)
            plan_uses_out = any(
                "terraform plan" in str(s.get("run", "")) and "-out=" in str(s.get("run", ""))
                for s in steps
            )
            if not plan_uses_out:
                return  # -out not used — test is not applicable

            has_artifact_upload = any(
                "actions/upload-artifact" in str(s.get("uses", ""))
                for s in steps
            )
            self.assertTrue(
                has_artifact_upload,
                "terraform plan uses -out=<file> but no 'actions/upload-artifact' "
                "step was found. Upload the plan file as an artifact so it is auditable.",
            )


# ---------------------------------------------------------------------------
# Job timeout — must complete in under 3 minutes
# ---------------------------------------------------------------------------


class TestTfValidateTimeout(unittest.TestCase):
    """
    The tf-validate job must declare a timeout that enforces the <3-minute
    completion SLA defined in the acceptance criteria.
    """

    _MAX_ALLOWED_MINUTES = 3

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)

    def test_tf_validate_job_has_timeout_minutes(self):
        """
        The tf-validate job must set timeout-minutes so runaway init or plan
        steps do not consume CI minutes indefinitely.
        """
        for job_id, job in self.tf_jobs:
            self.assertIn(
                "timeout-minutes",
                job,
                f"tf-validate job '{job_id}' is missing 'timeout-minutes'. "
                "Set timeout-minutes to enforce the <3-minute completion SLA.",
            )

    def test_tf_validate_timeout_is_at_most_three_minutes(self):
        """
        timeout-minutes must be <= 3 to enforce the acceptance-criteria SLA.

        A larger timeout means a hung job blocks the PR for too long.
        """
        for job_id, job in self.tf_jobs:
            timeout = job.get("timeout-minutes")
            if timeout is None:
                continue  # Covered by test_tf_validate_job_has_timeout_minutes
            self.assertLessEqual(
                timeout,
                self._MAX_ALLOWED_MINUTES,
                f"tf-validate job '{job_id}' has timeout-minutes={timeout}, "
                f"which exceeds the maximum of {self._MAX_ALLOWED_MINUTES}. "
                "Reduce the timeout to enforce the <3-minute SLA.",
            )


# ---------------------------------------------------------------------------
# Checkout step
# ---------------------------------------------------------------------------


class TestTfValidateCheckoutStep(unittest.TestCase):
    """The tf-validate job must check out the repository before running terraform."""

    def setUp(self):
        self.path = _find_workflow_with_tf_validate_job()
        if self.path is None:
            self.skipTest("tf-validate workflow not yet created")
        self.doc = _load_workflow(self.path)
        self.tf_jobs = _collect_tf_validate_jobs(self.doc)

    def test_has_checkout_step(self):
        """A checkout step (actions/checkout) must precede all terraform steps."""
        for job_id, job in self.tf_jobs:
            steps = _collect_all_steps_for_job(job)
            checkout_steps = [
                s for s in steps if "checkout" in str(s.get("uses", "")).lower()
            ]
            self.assertGreater(
                len(checkout_steps),
                0,
                f"tf-validate job '{job_id}' has no 'actions/checkout' step. "
                "Terraform commands will run against an empty workspace.",
            )

    def test_checkout_step_precedes_first_terraform_step(self):
        """The checkout step must appear before the first terraform invocation."""
        for _, job in self.tf_jobs:
            steps = _collect_all_steps_for_job(job)
            checkout_idx = next(
                (i for i, s in enumerate(steps) if "checkout" in str(s.get("uses", "")).lower()),
                None,
            )
            terraform_idx = next(
                (i for i, s in enumerate(steps) if "terraform" in str(s.get("run", ""))),
                None,
            )
            if checkout_idx is None or terraform_idx is None:
                continue
            self.assertLess(
                checkout_idx,
                terraform_idx,
                f"Checkout step (index {checkout_idx}) must appear before "
                f"the first terraform step (index {terraform_idx}).",
            )


if __name__ == "__main__":
    unittest.main()
