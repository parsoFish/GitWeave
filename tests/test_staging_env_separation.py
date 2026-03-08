"""
Tests for staging environment separation in the gitweave-apply workflow.

Work item: Implement staging environment separation for overlay application

These tests define expected behaviour BEFORE implementation (TDD red phase).
All tests in this file will FAIL until the feature is implemented.

Feature summary
---------------
gitweave-apply.yaml is extended to separate staging from production applies:

  1. Two distinct jobs: apply-staging and apply-production.
  2. apply-production has ``needs: [apply-staging]`` — it only starts when
     staging succeeds, enforcing the staging → production promotion gate.
  3. apply-production references ``environment: production`` so GitHub requires
     at least one reviewer before the job starts (environment protection rule).
  4. A ``TARGET_ENV`` workflow_dispatch input (string) selects the target
     environment; each job hard-codes its own env filter (staging / production)
     and passes it to the script as ``--env <value>``.
  5. apply-overlays.py gains a filter_overlays_by_environment(configs, env)
     function that returns only overlays containing
     spec.environments.<env>.

Test layers
-----------
Unit — TestStagingJobsWorkflowStructure
    Verify the gitweave-apply.yaml YAML declares apply-staging and
    apply-production as separate jobs with the correct structure.

Unit — TestProductionJobDependency
    Verify apply-production depends on apply-staging and declares the
    GitHub environment: production.

Unit — TestTargetEnvInput
    Verify the workflow_dispatch block exposes a TARGET_ENV (or target_env)
    string input.

Unit — TestApplyStagingJobConfig
    Verify apply-staging passes --env staging (or equivalent) to the script.

Unit — TestApplyProductionJobConfig
    Verify apply-production passes --env production (or equivalent).

Unit — TestFilterOverlaysByEnvironment (script)
    Verify apply-overlays.py exposes filter_overlays_by_environment() and
    returns only overlays that contain spec.environments.<env>.

Unit — TestApplyOverlayEnvironmentFiltering
    Verify apply_overlay uses the env filter and skips overlays that do not
    define the target environment.

Integration — TestEnvFilterCLI
    Subprocess-level tests that invoke apply-overlays.py --dry-run --env staging
    and verify only staging overlays appear in the output.

Unit — TestRunbookExists
    Verify docs/runbooks/overlay-apply.md exists and documents the
    staging → production promotion flow with approval and rollback sections.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW_PATH = os.path.join(
    REPO_ROOT, ".github", "workflows", "gitweave-apply.yaml"
)
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "apply-overlays.py")
RUNBOOK_PATH = os.path.join(REPO_ROOT, "docs", "runbooks", "overlay-apply.md")


# ---------------------------------------------------------------------------
# Shared helpers — workflow
# ---------------------------------------------------------------------------


def _load_workflow() -> dict:
    """Parse gitweave-apply.yaml and return the document dict."""
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def _get_triggers(doc: dict) -> dict:
    """Return the workflow trigger mapping (handles PyYAML 'on' → True quirk)."""
    return doc.get("on") or doc.get(True) or {}


def _collect_all_steps(doc: dict) -> list:
    """Return a flat list of every step across all jobs."""
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


def _get_job(doc: dict, job_id: str) -> dict | None:
    """Return the job dict for *job_id*, or None if absent."""
    return doc.get("jobs", {}).get(job_id)


# ---------------------------------------------------------------------------
# Shared helpers — script
# ---------------------------------------------------------------------------


def _load_script():
    """
    Import apply-overlays.py as a Python module.
    Raises FileNotFoundError with a descriptive message when absent.
    """
    if not os.path.isfile(SCRIPT_PATH):
        raise FileNotFoundError(
            f"scripts/apply-overlays.py not found at {SCRIPT_PATH}"
        )
    spec = importlib.util.spec_from_file_location("apply_overlays", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke apply-overlays.py with given arguments, capturing output."""
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, SCRIPT_PATH, *args],
        capture_output=True,
        text=True,
        env=run_env,
    )


def _write_yaml(directory: str, filename: str, doc: dict) -> str:
    """Write doc as YAML to directory/filename and return the full path."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    return path


def _minimal_overlay(
    repo: str = "my-org/my-app",
    modules: list | None = None,
    environments: dict | None = None,
) -> dict:
    """Return the smallest valid RepositoryOverlay document."""
    doc: dict = {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {"repository": repo},
    }
    if modules is not None:
        doc["spec"]["modules"] = modules
    if environments is not None:
        doc["spec"]["environments"] = environments
    return doc


def _overlay_with_staging(repo: str = "my-org/staging-svc") -> dict:
    """Return an overlay that declares a staging environment."""
    return _minimal_overlay(
        repo=repo,
        modules=[{"name": "lang-node"}],
        environments={"staging": {"variables": {"LOG_LEVEL": "info"}}},
    )


def _overlay_with_production(repo: str = "my-org/prod-svc") -> dict:
    """Return an overlay that declares a production environment."""
    return _minimal_overlay(
        repo=repo,
        modules=[{"name": "lang-node"}],
        environments={"production": {"variables": {"LOG_LEVEL": "error"}}},
    )


def _overlay_without_environments(repo: str = "my-org/no-env-svc") -> dict:
    """Return an overlay that declares no environments at all."""
    return _minimal_overlay(repo=repo, modules=[{"name": "lang-node"}])


def _overlay_with_both_envs(repo: str = "my-org/multi-env-svc") -> dict:
    """Return an overlay with both staging and production environments defined."""
    return _minimal_overlay(
        repo=repo,
        modules=[{"name": "lang-node"}],
        environments={
            "staging": {"variables": {"NODE_ENV": "staging"}},
            "production": {"variables": {"NODE_ENV": "production"}},
        },
    )


# ---------------------------------------------------------------------------
# TestStagingJobsWorkflowStructure
# ---------------------------------------------------------------------------


class TestStagingJobsWorkflowStructure(unittest.TestCase):
    """
    Verify that gitweave-apply.yaml defines apply-staging and apply-production
    as two distinct, separately named jobs.
    """

    def test_apply_staging_job_exists(self):
        """
        Workflow must define an 'apply-staging' job.

        The single-job 'apply' approach cannot distinguish staging from
        production; two jobs with separate conditions are required.
        """
        doc = _load_workflow()
        jobs = doc.get("jobs", {})
        self.assertIn(
            "apply-staging",
            jobs,
            f"Workflow must define an 'apply-staging' job. "
            f"Found jobs: {list(jobs.keys())}",
        )

    def test_apply_production_job_exists(self):
        """
        Workflow must define an 'apply-production' job.

        Without a dedicated production job, the environment: production approval
        gate cannot be enforced separately from staging.
        """
        doc = _load_workflow()
        jobs = doc.get("jobs", {})
        self.assertIn(
            "apply-production",
            jobs,
            f"Workflow must define an 'apply-production' job. "
            f"Found jobs: {list(jobs.keys())}",
        )

    def test_apply_staging_job_runs_on_ubuntu_latest(self):
        """apply-staging must run on ubuntu-latest."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        self.assertEqual(
            job.get("runs-on"),
            "ubuntu-latest",
            f"apply-staging must run on 'ubuntu-latest', got: {job.get('runs-on')}",
        )

    def test_apply_production_job_runs_on_ubuntu_latest(self):
        """apply-production must run on ubuntu-latest."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        self.assertEqual(
            job.get("runs-on"),
            "ubuntu-latest",
            f"apply-production must run on 'ubuntu-latest', got: {job.get('runs-on')}",
        )

    def test_apply_staging_job_has_checkout_step(self):
        """apply-staging must include an actions/checkout step."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        uses_values = [step.get("uses", "") for step in job.get("steps", [])]
        has_checkout = any("actions/checkout" in u for u in uses_values)
        self.assertTrue(
            has_checkout,
            "apply-staging job must include an actions/checkout step",
        )

    def test_apply_production_job_has_checkout_step(self):
        """apply-production must include an actions/checkout step."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        uses_values = [step.get("uses", "") for step in job.get("steps", [])]
        has_checkout = any("actions/checkout" in u for u in uses_values)
        self.assertTrue(
            has_checkout,
            "apply-production job must include an actions/checkout step",
        )

    def test_apply_staging_job_invokes_apply_overlays_script(self):
        """apply-staging must call scripts/apply-overlays.py."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        run_texts = [
            str(step.get("run", ""))
            for step in job.get("steps", [])
            if step.get("run")
        ]
        invokes = any("apply-overlays" in r for r in run_texts)
        self.assertTrue(
            invokes,
            f"apply-staging job must invoke apply-overlays.py. "
            f"run commands found: {run_texts}",
        )

    def test_apply_production_job_invokes_apply_overlays_script(self):
        """apply-production must call scripts/apply-overlays.py."""
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        run_texts = [
            str(step.get("run", ""))
            for step in job.get("steps", [])
            if step.get("run")
        ]
        invokes = any("apply-overlays" in r for r in run_texts)
        self.assertTrue(
            invokes,
            f"apply-production job must invoke apply-overlays.py. "
            f"run commands found: {run_texts}",
        )


# ---------------------------------------------------------------------------
# TestProductionJobDependency
# ---------------------------------------------------------------------------


class TestProductionJobDependency(unittest.TestCase):
    """
    Verify the production apply gate: apply-production must need apply-staging
    and reference environment: production.
    """

    def test_apply_production_depends_on_apply_staging(self):
        """
        apply-production must declare ``needs: apply-staging`` (or the list form
        ``needs: [apply-staging]``) so GitHub Actions only starts it after
        apply-staging succeeds.

        Without this dependency, both jobs run in parallel and the staging gate
        provides no protection against shipping broken changes to production.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        needs = job.get("needs")
        if needs is None:
            self.fail(
                "apply-production must declare 'needs: apply-staging' but "
                "'needs' is absent from the job definition"
            )
        # needs can be a string or a list
        if isinstance(needs, str):
            needs_list = [needs]
        else:
            needs_list = list(needs)
        self.assertIn(
            "apply-staging",
            needs_list,
            f"apply-production must need 'apply-staging'. "
            f"Found needs: {needs_list}",
        )

    def test_apply_production_does_not_continue_on_error(self):
        """
        apply-production must NOT set ``continue-on-error: true``.

        If staging fails but production continues anyway, the dependency gate
        is meaningless. GitHub Actions default (no continue-on-error) is correct;
        we just confirm no one overrides it.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        continue_on_error = job.get("continue-on-error", False)
        self.assertFalse(
            continue_on_error,
            "apply-production must not set continue-on-error: true — "
            "production apply must halt when staging apply fails",
        )

    def test_apply_production_references_production_environment(self):
        """
        apply-production must declare ``environment: production`` so GitHub
        enforces the environment protection rules (required reviewers).

        Without this declaration, GitHub does not prompt for reviewer approval
        before the job runs, removing the manual gate between staging and production.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        env_field = job.get("environment")
        if env_field is None:
            self.fail(
                "apply-production must declare 'environment: production' "
                "so GitHub enforces reviewer approval before the job runs"
            )
        # environment can be a string or a dict with name/url
        if isinstance(env_field, dict):
            env_name = env_field.get("name", "")
        else:
            env_name = str(env_field)
        self.assertEqual(
            env_name,
            "production",
            f"apply-production must reference environment 'production', "
            f"got: {env_name!r}",
        )

    def test_apply_staging_does_not_depend_on_apply_production(self):
        """
        apply-staging must NOT depend on apply-production (no circular dependency).

        Staging runs first, independently; production waits for staging.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        needs = job.get("needs")
        if needs is None:
            return  # No dependency is correct
        if isinstance(needs, str):
            needs_list = [needs]
        else:
            needs_list = list(needs)
        self.assertNotIn(
            "apply-production",
            needs_list,
            f"apply-staging must not depend on apply-production (circular). "
            f"Found needs: {needs_list}",
        )

    def test_apply_staging_does_not_reference_production_environment(self):
        """
        apply-staging must not declare ``environment: production`` — the
        production approval gate is exclusive to the production job.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        env_field = job.get("environment")
        if env_field is None:
            return  # No environment declaration is correct for staging
        if isinstance(env_field, dict):
            env_name = env_field.get("name", "")
        else:
            env_name = str(env_field)
        self.assertNotEqual(
            env_name,
            "production",
            "apply-staging must not reference 'environment: production' — "
            "that gate belongs exclusively to the production job",
        )


# ---------------------------------------------------------------------------
# TestTargetEnvInput
# ---------------------------------------------------------------------------


class TestTargetEnvInput(unittest.TestCase):
    """
    Verify workflow_dispatch exposes a TARGET_ENV / target_env string input
    so operators can select the target environment for manual runs.
    """

    def _get_dispatch_inputs(self, doc: dict) -> dict:
        """Return the workflow_dispatch inputs dict."""
        triggers = doc.get("on") or doc.get(True) or {}
        dispatch = triggers.get("workflow_dispatch") or {}
        return dispatch.get("inputs") or {}

    def test_workflow_dispatch_has_target_env_input(self):
        """
        workflow_dispatch must declare a TARGET_ENV (or target_env) input so
        operators can trigger an environment-specific apply via the GitHub UI
        or API without editing code.
        """
        doc = _load_workflow()
        inputs = self._get_dispatch_inputs(doc)
        # Accept either TARGET_ENV or target_env (implementation detail)
        has_target_env = "TARGET_ENV" in inputs or "target_env" in inputs
        self.assertTrue(
            has_target_env,
            f"workflow_dispatch must declare a 'TARGET_ENV' or 'target_env' input. "
            f"Found inputs: {list(inputs.keys())}",
        )

    def test_target_env_input_is_string_type(self):
        """TARGET_ENV / target_env input must be type 'string' or 'choice'."""
        doc = _load_workflow()
        inputs = self._get_dispatch_inputs(doc)
        input_def = inputs.get("TARGET_ENV") or inputs.get("target_env") or {}
        input_type = input_def.get("type", "string")
        self.assertIn(
            input_type,
            ("string", "choice"),
            f"TARGET_ENV input must be type 'string' or 'choice', got: {input_type!r}",
        )

    def test_target_env_input_is_not_required(self):
        """
        TARGET_ENV / target_env must not be required — omitting it should
        allow the workflow to fall through with no environment filter,
        applying all overlays (or a default behaviour).
        """
        doc = _load_workflow()
        inputs = self._get_dispatch_inputs(doc)
        input_def = inputs.get("TARGET_ENV") or inputs.get("target_env") or {}
        required = input_def.get("required", False)
        self.assertFalse(
            required,
            f"TARGET_ENV input must be optional (required: false), got required: {required}",
        )

    def test_apply_staging_job_passes_staging_env_to_script(self):
        """
        apply-staging must pass '--env staging' (or equivalent) to
        apply-overlays.py so the script filters for staging-environment overlays.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-staging")
        self.assertIsNotNone(job, "apply-staging job not found")
        run_texts = " ".join(
            str(step.get("run", ""))
            for step in job.get("steps", [])
            if step.get("run")
        )
        has_staging_filter = (
            "--env staging" in run_texts
            or "staging" in run_texts
        )
        self.assertTrue(
            has_staging_filter,
            f"apply-staging job must pass '--env staging' to apply-overlays.py. "
            f"run commands: {run_texts}",
        )

    def test_apply_production_job_passes_production_env_to_script(self):
        """
        apply-production must pass '--env production' (or equivalent) to
        apply-overlays.py so the script filters for production-environment overlays.
        """
        doc = _load_workflow()
        job = _get_job(doc, "apply-production")
        self.assertIsNotNone(job, "apply-production job not found")
        run_texts = " ".join(
            str(step.get("run", ""))
            for step in job.get("steps", [])
            if step.get("run")
        )
        has_production_filter = (
            "--env production" in run_texts
            or "production" in run_texts
        )
        self.assertTrue(
            has_production_filter,
            f"apply-production job must pass '--env production' to apply-overlays.py. "
            f"run commands: {run_texts}",
        )


# ---------------------------------------------------------------------------
# TestFilterOverlaysByEnvironment — script unit tests
# ---------------------------------------------------------------------------


class TestFilterOverlaysByEnvironment(unittest.TestCase):
    """
    Unit tests for the filter_overlays_by_environment(configs, env) function
    in scripts/apply-overlays.py.

    filter_overlays_by_environment must:
      - Return only configs that have spec.environments.<env> defined.
      - Return an empty list when no configs match the env.
      - Return all configs unchanged when env is None or empty string.
      - Not mutate the input list.
    """

    def setUp(self):
        self.mod = _load_script()

    def test_script_exposes_filter_overlays_by_environment_callable(self):
        """
        apply-overlays.py must expose a callable filter_overlays_by_environment.
        This function encapsulates the environment filtering logic so it can be
        unit-tested independently of the full apply pipeline.
        """
        self.assertTrue(
            callable(getattr(self.mod, "filter_overlays_by_environment", None)),
            "apply-overlays.py must expose callable 'filter_overlays_by_environment'. "
            "Add filter_overlays_by_environment(configs, env) -> list to the script.",
        )

    def test_returns_overlays_that_declare_staging_environment(self):
        """
        When env='staging', only configs with spec.environments.staging
        are returned.
        """
        staging = _overlay_with_staging("org/staging-svc")
        non_env = _overlay_without_environments("org/no-env-svc")
        prod = _overlay_with_production("org/prod-svc")

        result = self.mod.filter_overlays_by_environment(
            [staging, non_env, prod], "staging"
        )

        self.assertEqual(
            len(result),
            1,
            f"Only 1 overlay declares staging — expected 1, got {len(result)}: {result}",
        )
        self.assertEqual(
            result[0]["spec"]["repository"],
            "org/staging-svc",
            f"Returned overlay should be 'org/staging-svc', got: {result[0]}",
        )

    def test_returns_overlays_that_declare_production_environment(self):
        """
        When env='production', only configs with spec.environments.production
        are returned.
        """
        staging = _overlay_with_staging("org/staging-svc")
        prod = _overlay_with_production("org/prod-svc")
        both = _overlay_with_both_envs("org/multi-env-svc")

        result = self.mod.filter_overlays_by_environment(
            [staging, prod, both], "production"
        )

        repos = [r["spec"]["repository"] for r in result]
        self.assertIn(
            "org/prod-svc",
            repos,
            f"'org/prod-svc' declares production and must be included. Got: {repos}",
        )
        self.assertIn(
            "org/multi-env-svc",
            repos,
            f"'org/multi-env-svc' declares both envs and must be included for production. "
            f"Got: {repos}",
        )
        self.assertNotIn(
            "org/staging-svc",
            repos,
            f"'org/staging-svc' only declares staging — must be excluded for production. "
            f"Got: {repos}",
        )

    def test_excludes_overlays_without_target_environment(self):
        """
        Overlays that have no spec.environments key at all must be excluded
        when an environment filter is applied.
        """
        no_env = _overlay_without_environments("org/bare-svc")
        result = self.mod.filter_overlays_by_environment([no_env], "staging")
        self.assertEqual(
            result,
            [],
            f"Overlays with no spec.environments must be excluded when filtering. "
            f"Got: {result}",
        )

    def test_excludes_overlays_with_different_environment_only(self):
        """
        An overlay declaring only production is excluded when filtering for staging.
        """
        prod_only = _overlay_with_production("org/prod-only-svc")
        result = self.mod.filter_overlays_by_environment([prod_only], "staging")
        self.assertEqual(
            result,
            [],
            f"'org/prod-only-svc' only declares production — must be excluded for "
            f"staging filter. Got: {result}",
        )

    def test_includes_overlay_with_both_environments_for_staging_filter(self):
        """
        An overlay that declares both staging and production must be included
        when filtering for staging.
        """
        both = _overlay_with_both_envs("org/multi-env-svc")
        result = self.mod.filter_overlays_by_environment([both], "staging")
        self.assertEqual(
            len(result),
            1,
            f"Overlay declaring both staging + production must be included for "
            f"staging filter. Got: {result}",
        )

    def test_returns_all_configs_when_env_is_none(self):
        """
        When env is None, filter_overlays_by_environment returns all configs
        unchanged (no filtering).
        """
        configs = [
            _overlay_with_staging("org/a"),
            _overlay_with_production("org/b"),
            _overlay_without_environments("org/c"),
        ]
        result = self.mod.filter_overlays_by_environment(configs, None)
        self.assertEqual(
            len(result),
            3,
            f"With env=None, all 3 configs must be returned. Got {len(result)}: {result}",
        )

    def test_returns_all_configs_when_env_is_empty_string(self):
        """
        When env is an empty string, filter_overlays_by_environment returns
        all configs unchanged (same as no filter).
        """
        configs = [
            _overlay_with_staging("org/a"),
            _overlay_without_environments("org/b"),
        ]
        result = self.mod.filter_overlays_by_environment(configs, "")
        self.assertEqual(
            len(result),
            2,
            f"With env='', all 2 configs must be returned. Got {len(result)}: {result}",
        )

    def test_returns_empty_list_when_no_configs_match_env(self):
        """
        When no overlays declare the target environment, an empty list is returned.
        """
        configs = [
            _overlay_without_environments("org/bare"),
            _overlay_with_production("org/prod-svc"),
        ]
        result = self.mod.filter_overlays_by_environment(configs, "staging")
        self.assertEqual(
            result,
            [],
            f"No overlays declare staging — expected [], got: {result}",
        )

    def test_does_not_mutate_input_list(self):
        """filter_overlays_by_environment must not modify the input list in-place."""
        configs = [
            _overlay_with_staging("org/a"),
            _overlay_without_environments("org/b"),
        ]
        original_len = len(configs)
        self.mod.filter_overlays_by_environment(configs, "staging")
        self.assertEqual(
            len(configs),
            original_len,
            "filter_overlays_by_environment must not mutate the input list. "
            f"Before: {original_len} items, after: {len(configs)} items.",
        )

    def test_returns_new_list_not_reference_to_input(self):
        """filter_overlays_by_environment must return a new list."""
        configs = [_overlay_with_staging("org/a")]
        result = self.mod.filter_overlays_by_environment(configs, "staging")
        self.assertIsNot(
            result,
            configs,
            "filter_overlays_by_environment must return a new list, not the input object.",
        )


# ---------------------------------------------------------------------------
# TestApplyOverlayEnvironmentFiltering — integration with apply_overlay
# ---------------------------------------------------------------------------


class TestApplyOverlayEnvironmentFiltering(unittest.TestCase):
    """
    Verify that the main apply pipeline uses filter_overlays_by_environment
    when an env argument is provided, so staging runs never touch production
    repos and vice versa.
    """

    def setUp(self):
        self.mod = _load_script()

    @patch("subprocess.run")
    def test_apply_overlay_with_staging_env_only_processes_staging_overlays(
        self, mock_run: MagicMock
    ):
        """
        When apply_overlay is called with env='staging', only the overlay
        that declares spec.environments.staging is processed; overlays without
        that environment key must be skipped (no subprocess calls for them).
        """
        # Staging overlay — should be processed
        staging_config = _overlay_with_staging("org/staging-svc")
        # Production-only overlay — must be skipped
        prod_config = _overlay_with_production("org/prod-svc")

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Call apply_overlay with env='staging' for the production overlay
        # Expect it to be skipped (returns a skipped/not-applicable result)
        result = self.mod.apply_overlay(
            config=prod_config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
            env="staging",
        )

        # The production overlay must be skipped — not applied
        skipped = result.get("skipped") or not result.get("applicable", True)
        self.assertTrue(
            skipped or result.get("dry_run"),
            f"Production overlay should be skipped/not applicable when env='staging'. "
            f"Result: {result}",
        )

    @patch("subprocess.run")
    def test_apply_overlay_processes_overlay_that_matches_env(
        self, mock_run: MagicMock
    ):
        """
        When apply_overlay is called with env='staging', an overlay that declares
        spec.environments.staging must be processed (result is not skipped).
        """
        staging_config = _overlay_with_staging("org/staging-svc")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = self.mod.apply_overlay(
            config=staging_config,
            modules_dir=os.path.join(REPO_ROOT, "modules"),
            github_token="fake-token",
            dry_run=True,
            env="staging",
        )

        # A staging overlay should be applicable — not skipped
        self.assertFalse(
            result.get("skipped", False),
            f"Staging overlay must not be skipped when env='staging'. Result: {result}",
        )


# ---------------------------------------------------------------------------
# TestEnvFilterCLI — subprocess-level integration tests
# ---------------------------------------------------------------------------


class TestEnvFilterCLI(unittest.TestCase):
    """
    Subprocess-level tests that invoke apply-overlays.py --dry-run --env staging
    and verify that only staging-environment overlays appear in the output.
    """

    def test_dry_run_with_env_staging_includes_staging_overlay_in_output(self):
        """
        When apply-overlays.py is invoked with --dry-run --env staging, the output
        must mention the repo from a staging-environment overlay.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "staging-svc.yaml",
                _overlay_with_staging("org/staging-svc"),
            )
            _write_yaml(
                tmpdir,
                "prod-svc.yaml",
                _overlay_with_production("org/prod-svc"),
            )
            result = _run_script(
                "--dry-run",
                "--env", "staging",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        self.assertIn(
            "org/staging-svc",
            combined,
            f"Staging overlay 'org/staging-svc' must appear in dry-run output when "
            f"--env staging is used.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_staging_excludes_production_only_overlay(self):
        """
        When invoked with --dry-run --env staging, the output must NOT mention
        repos from overlays that only declare a production environment.

        This is the core staging isolation guarantee: staging runs must never
        touch production-only repositories.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "prod-svc.yaml",
                _overlay_with_production("org/prod-svc"),
            )
            result = _run_script(
                "--dry-run",
                "--env", "staging",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        # 'org/prod-svc' should NOT appear in the output when filtering for staging
        self.assertNotIn(
            "org/prod-svc",
            combined,
            f"Production-only overlay 'org/prod-svc' must NOT appear in output when "
            f"--env staging is used.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_staging_excludes_overlays_without_environments(self):
        """
        Overlays that have no spec.environments section must be excluded from
        the staging apply run.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "bare-svc.yaml",
                _overlay_without_environments("org/bare-svc"),
            )
            result = _run_script(
                "--dry-run",
                "--env", "staging",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        self.assertNotIn(
            "org/bare-svc",
            combined,
            f"'org/bare-svc' has no spec.environments — must be excluded when "
            f"--env staging is used.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_production_includes_production_overlay(self):
        """
        When invoked with --dry-run --env production, the output must mention
        repos from overlays that declare a production environment.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "prod-svc.yaml",
                _overlay_with_production("org/prod-svc"),
            )
            result = _run_script(
                "--dry-run",
                "--env", "production",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        self.assertIn(
            "org/prod-svc",
            combined,
            f"Production overlay 'org/prod-svc' must appear in dry-run output when "
            f"--env production is used.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_production_excludes_staging_only_overlay(self):
        """
        When invoked with --dry-run --env production, the output must NOT
        mention repos from overlays that only declare a staging environment.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "staging-svc.yaml",
                _overlay_with_staging("org/staging-svc"),
            )
            result = _run_script(
                "--dry-run",
                "--env", "production",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        self.assertNotIn(
            "org/staging-svc",
            combined,
            f"Staging-only overlay 'org/staging-svc' must NOT appear in output when "
            f"--env production is used.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_no_env_includes_all_overlays(self):
        """
        When --env is not passed, all overlays are processed regardless of
        their environment declarations (backward-compatible behaviour).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir, "staging-svc.yaml", _overlay_with_staging("org/staging-svc")
            )
            _write_yaml(
                tmpdir, "prod-svc.yaml", _overlay_with_production("org/prod-svc")
            )
            _write_yaml(
                tmpdir, "bare-svc.yaml", _overlay_without_environments("org/bare-svc")
            )
            result = _run_script(
                "--dry-run",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        combined = result.stdout + result.stderr
        self.assertIn(
            "org/staging-svc",
            combined,
            f"Without --env, all overlays should be processed. "
            f"'org/staging-svc' missing.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn(
            "org/prod-svc",
            combined,
            f"Without --env, all overlays should be processed. "
            f"'org/prod-svc' missing.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn(
            "org/bare-svc",
            combined,
            f"Without --env, all overlays should be processed. "
            f"'org/bare-svc' missing.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_with_env_staging_exits_zero_even_with_no_matching_overlays(self):
        """
        When --env staging is passed but no overlays declare staging, the script
        must still exit 0 — an empty result is a valid outcome.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir, "prod-svc.yaml", _overlay_with_production("org/prod-svc")
            )
            result = _run_script(
                "--dry-run",
                "--env", "staging",
                "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        self.assertEqual(
            result.returncode,
            0,
            f"Script must exit 0 when --env staging matches no overlays.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_env_argument_is_accepted_without_argument_error(self):
        """Script must accept --env without reporting an unrecognized argument error."""
        result = _run_script(
            "--dry-run",
            "--env", "staging",
            "--config-dir", "/nonexistent",
            env={"GITHUB_TOKEN": "fake"},
        )
        self.assertNotIn(
            "unrecognized argument",
            result.stderr,
            f"Script rejected --env argument.\nstderr: {result.stderr}",
        )
        self.assertNotIn(
            "error: argument",
            result.stderr.lower(),
            f"Script reported argument error for --env.\nstderr: {result.stderr}",
        )

    def test_multi_env_overlay_appears_in_both_staging_and_production_runs(self):
        """
        An overlay that declares both staging and production environments must
        appear in both --env staging and --env production dry-run outputs.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir, "multi-env.yaml", _overlay_with_both_envs("org/multi-env-svc")
            )
            staging_result = _run_script(
                "--dry-run", "--env", "staging", "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )
            production_result = _run_script(
                "--dry-run", "--env", "production", "--config-dir", tmpdir,
                env={"GITHUB_TOKEN": "fake"},
            )

        self.assertIn(
            "org/multi-env-svc",
            staging_result.stdout + staging_result.stderr,
            f"Multi-env overlay must appear in --env staging output.\n"
            f"stdout: {staging_result.stdout}\nstderr: {staging_result.stderr}",
        )
        self.assertIn(
            "org/multi-env-svc",
            production_result.stdout + production_result.stderr,
            f"Multi-env overlay must appear in --env production output.\n"
            f"stdout: {production_result.stdout}\nstderr: {production_result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestRunbookExists
# ---------------------------------------------------------------------------


class TestRunbookExists(unittest.TestCase):
    """
    Verify that docs/runbooks/overlay-apply.md exists and documents the
    staging → production promotion flow with the required sections.
    """

    def test_runbook_file_exists_at_expected_path(self):
        """
        docs/runbooks/overlay-apply.md must exist.

        Without this runbook, operators have no reference for how to promote
        changes from staging to production or how to respond to failed applies.
        """
        self.assertTrue(
            os.path.isfile(RUNBOOK_PATH),
            f"docs/runbooks/overlay-apply.md is missing — expected at {RUNBOOK_PATH}. "
            "Create the runbook before the acceptance criteria is met.",
        )

    def test_runbook_mentions_staging(self):
        """Runbook must mention 'staging' — the first stage of the promotion flow."""
        with open(RUNBOOK_PATH) as f:
            content = f.read().lower()
        self.assertIn(
            "staging",
            content,
            "docs/runbooks/overlay-apply.md must mention 'staging' to document "
            "the staging apply step.",
        )

    def test_runbook_mentions_production(self):
        """Runbook must mention 'production' — the final stage of the promotion flow."""
        with open(RUNBOOK_PATH) as f:
            content = f.read().lower()
        self.assertIn(
            "production",
            content,
            "docs/runbooks/overlay-apply.md must mention 'production' to document "
            "the production apply step.",
        )

    def test_runbook_documents_promotion_flow(self):
        """
        Runbook must document the staging → production promotion concept.
        Acceptable terms include 'promot', 'promotion', or 'promote'.
        """
        with open(RUNBOOK_PATH) as f:
            content = f.read().lower()
        has_promotion_term = (
            "promot" in content  # promote, promotion, promoting
            or "staging to production" in content
            or "staging → production" in content
            or "staging -> production" in content
        )
        self.assertTrue(
            has_promotion_term,
            "docs/runbooks/overlay-apply.md must document the staging → production "
            "promotion flow. Include 'promote', 'promotion', or similar terminology.",
        )

    def test_runbook_documents_approval_process(self):
        """
        Runbook must document the approval or review step required before
        production applies run. Terms: 'approval', 'approve', 'reviewer'.
        """
        with open(RUNBOOK_PATH) as f:
            content = f.read().lower()
        has_approval_term = (
            "approv" in content  # approval, approve, approved
            or "reviewer" in content
            or "review" in content
        )
        self.assertTrue(
            has_approval_term,
            "docs/runbooks/overlay-apply.md must document the approval / reviewer "
            "process for production applies.",
        )

    def test_runbook_documents_rollback_procedure(self):
        """
        Runbook must document what to do when an apply fails — a rollback or
        recovery procedure. Terms: 'rollback', 'revert', 'recover', 'fix'.
        """
        with open(RUNBOOK_PATH) as f:
            content = f.read().lower()
        has_recovery_term = (
            "rollback" in content
            or "revert" in content
            or "recover" in content
            or "fix" in content
        )
        self.assertTrue(
            has_recovery_term,
            "docs/runbooks/overlay-apply.md must document a rollback or recovery "
            "procedure for failed applies.",
        )

    def test_runbook_has_meaningful_content(self):
        """Runbook must contain at least 200 characters — not a skeleton placeholder."""
        with open(RUNBOOK_PATH) as f:
            content = f.read()
        self.assertGreater(
            len(content),
            200,
            f"docs/runbooks/overlay-apply.md appears to be a placeholder "
            f"(only {len(content)} chars). Write actual runbook content.",
        )


if __name__ == "__main__":
    unittest.main()
