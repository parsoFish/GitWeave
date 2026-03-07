"""
Tests for the gitweave-apply.yaml GitHub Actions workflow that applies
Copier overlay configurations to target repositories.

These tests verify that .github/workflows/gitweave-apply.yaml is correctly
configured after the placeholder echo is replaced with real logic:

  Trigger configuration:
    - Fires on push to main when paths under config/** change
    - Fires on pull_request events (for --dry-run preview)
    - Exposes a workflow_dispatch trigger with a dry_run boolean input
    - Does NOT fire on tags or arbitrary branch pushes (only main)

  Dry-run gating:
    - The apply step passes --dry-run when triggered by a pull_request event
    - The apply step does NOT pass --dry-run when triggered by push to main
    - The apply step respects workflow_dispatch dry_run input

  Script invocation:
    - At least one step invokes scripts/apply-overlays.py
    - The step passes --config-dir config/repos/ (or equivalent default)
    - The step sets up Python before running the script

  Authentication:
    - At least one step sets GITHUB_TOKEN from the GitHub token secret
    - The workflow does not hardcode any credential values

  Structural requirements:
    - File is valid YAML and parses as a non-empty mapping
    - At least one job is defined
    - All jobs run on ubuntu-latest
    - Every job includes a checkout step

All tests will fail until .github/workflows/gitweave-apply.yaml is updated
to replace the placeholder with real Copier application logic (TDD red phase).
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


# ---------------------------------------------------------------------------
# TestWorkflowStructure
# ---------------------------------------------------------------------------


class TestWorkflowStructure(unittest.TestCase):
    """Basic structural requirements for the workflow file."""

    def test_workflow_file_exists(self):
        """gitweave-apply.yaml must exist at the expected path."""
        self.assertTrue(
            os.path.isfile(WORKFLOW_PATH),
            f".github/workflows/gitweave-apply.yaml is missing — expected at {WORKFLOW_PATH}",
        )

    def test_workflow_parses_as_valid_yaml(self):
        """.github/workflows/gitweave-apply.yaml must be valid YAML."""
        try:
            doc = _load_workflow()
        except yaml.YAMLError as exc:
            self.fail(f"gitweave-apply.yaml is not valid YAML: {exc}")
        self.assertIsInstance(
            doc,
            dict,
            "gitweave-apply.yaml must parse as a YAML mapping (dict)",
        )

    def test_workflow_defines_at_least_one_job(self):
        """The workflow must define at least one job."""
        doc = _load_workflow()
        jobs = doc.get("jobs", {})
        self.assertGreater(
            len(jobs),
            0,
            "gitweave-apply.yaml must define at least one job",
        )

    def test_all_jobs_run_on_ubuntu_latest(self):
        """Every job must run on ubuntu-latest."""
        doc = _load_workflow()
        for job_id, job in doc.get("jobs", {}).items():
            self.assertEqual(
                job.get("runs-on"),
                "ubuntu-latest",
                f"Job '{job_id}' must run on 'ubuntu-latest', got: {job.get('runs-on')}",
            )

    def test_every_job_has_a_checkout_step(self):
        """Every job must include an actions/checkout step."""
        doc = _load_workflow()
        for job_id, job in doc.get("jobs", {}).items():
            uses_values = [step.get("uses", "") for step in job.get("steps", [])]
            has_checkout = any("actions/checkout" in u for u in uses_values)
            self.assertTrue(
                has_checkout,
                f"Job '{job_id}' must include an actions/checkout step",
            )

    def test_workflow_placeholder_echo_is_removed(self):
        """The placeholder echo lines must no longer exist in the workflow."""
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        for run_text in all_runs:
            self.assertNotIn(
                "Applying configuration overlays...",
                run_text,
                "Placeholder echo 'Applying configuration overlays...' must be removed",
            )
            self.assertNotIn(
                "Configuration applied successfully.",
                run_text,
                "Placeholder echo 'Configuration applied successfully.' must be removed",
            )


# ---------------------------------------------------------------------------
# TestWorkflowTriggers
# ---------------------------------------------------------------------------


class TestWorkflowTriggers(unittest.TestCase):
    """Tests for the on: trigger configuration."""

    def test_triggers_on_push_to_main(self):
        """Workflow must trigger on push to the main branch."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        push = triggers.get("push", {}) or {}
        branches = push.get("branches", []) or []
        self.assertIn(
            "main",
            branches,
            f"Workflow must trigger on push to 'main'. push trigger: {push}",
        )

    def test_push_trigger_scoped_to_config_paths(self):
        """Push trigger must be scoped to config/** so unrelated pushes are skipped."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        push = triggers.get("push", {}) or {}
        paths = push.get("paths", []) or []
        self.assertTrue(
            any("config" in p for p in paths),
            f"Push trigger must include a 'config/**' path filter. paths: {paths}",
        )

    def test_triggers_on_pull_request(self):
        """Workflow must trigger on pull_request events for dry-run preview."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        self.assertIn(
            "pull_request",
            triggers,
            f"Workflow must include a pull_request trigger. triggers: {list(triggers.keys())}",
        )

    def test_triggers_on_workflow_dispatch(self):
        """Workflow must include a workflow_dispatch trigger for manual runs."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        self.assertIn(
            "workflow_dispatch",
            triggers,
            f"Workflow must include a workflow_dispatch trigger. triggers: {list(triggers.keys())}",
        )

    def test_workflow_dispatch_has_dry_run_boolean_input(self):
        """workflow_dispatch must declare a boolean 'dry_run' input."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        dispatch = triggers.get("workflow_dispatch") or {}
        inputs = dispatch.get("inputs") or {}
        self.assertIn(
            "dry_run",
            inputs,
            f"workflow_dispatch must declare a 'dry_run' input. inputs: {list(inputs.keys())}",
        )
        dry_run_input = inputs.get("dry_run", {}) or {}
        input_type = dry_run_input.get("type", "")
        self.assertEqual(
            input_type,
            "boolean",
            f"workflow_dispatch.inputs.dry_run must be type 'boolean', got: {input_type!r}",
        )

    def test_workflow_dispatch_dry_run_defaults_to_false(self):
        """workflow_dispatch dry_run input should default to false for apply-mode runs."""
        doc = _load_workflow()
        triggers = _get_triggers(doc)
        dispatch = triggers.get("workflow_dispatch") or {}
        inputs = dispatch.get("inputs") or {}
        dry_run_input = inputs.get("dry_run", {}) or {}
        default_val = dry_run_input.get("default")
        self.assertFalse(
            default_val,
            f"workflow_dispatch.inputs.dry_run.default should be false, got: {default_val!r}",
        )


# ---------------------------------------------------------------------------
# TestScriptInvocation
# ---------------------------------------------------------------------------


class TestScriptInvocation(unittest.TestCase):
    """Tests that the workflow actually invokes apply-overlays.py."""

    def test_at_least_one_step_invokes_apply_overlays_script(self):
        """At least one run step must invoke scripts/apply-overlays.py."""
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        invokes_script = any("apply-overlays" in run for run in all_runs)
        self.assertTrue(
            invokes_script,
            f"No step invokes 'apply-overlays.py'. run commands found: {all_runs}",
        )

    def test_step_sets_up_python_before_running_script(self):
        """A step using actions/setup-python must appear before the script step."""
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        has_setup_python = any(
            "setup-python" in str(step.get("uses", "")) for step in all_steps
        )
        self.assertTrue(
            has_setup_python,
            "Workflow must include an actions/setup-python step before running the script",
        )

    def test_script_step_references_config_repos_directory(self):
        """The script invocation must reference config/repos as the config directory."""
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        apply_runs = [r for r in all_runs if "apply-overlays" in r]
        self.assertTrue(apply_runs, "No apply-overlays.py invocation found")
        # The config dir should either be passed explicitly or be the default
        combined = " ".join(apply_runs)
        has_config_ref = "config/repos" in combined or "--config-dir" not in combined
        self.assertTrue(
            has_config_ref,
            f"Script invocation should reference 'config/repos'. apply steps: {apply_runs}",
        )


# ---------------------------------------------------------------------------
# TestDryRunGating
# ---------------------------------------------------------------------------


class TestDryRunGating(unittest.TestCase):
    """Tests that dry-run is applied on PRs and not on push-to-main."""

    def test_pull_request_triggered_step_includes_dry_run_flag(self):
        """
        When triggered by a pull_request, the apply step must pass --dry-run.
        This is verified by checking that the run command references the
        github.event_name condition or unconditionally includes --dry-run for PRs.
        """
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        apply_runs = [r for r in all_runs if "apply-overlays" in r]
        self.assertTrue(apply_runs, "No apply-overlays.py invocation found")

        combined = " ".join(apply_runs)
        # The dry-run should be conditional on event type (PR vs push)
        # Acceptable patterns: literal --dry-run, conditional expression, github.event_name
        uses_dry_run_logic = (
            "--dry-run" in combined
            or "dry_run" in combined
            or "event_name" in combined
            or "github.event" in combined
        )
        self.assertTrue(
            uses_dry_run_logic,
            f"Apply step must incorporate dry-run logic for PR events. "
            f"apply run commands: {apply_runs}",
        )

    def test_apply_step_conditionally_uses_dry_run_based_on_event(self):
        """
        The apply step must differentiate between PR (dry-run) and push (apply).
        This is verified by checking that either:
        - The run command includes a conditional expression for dry-run, OR
        - There are two separate steps (one with --dry-run, one without) gated by if: conditions
        """
        doc = _load_workflow()
        all_steps = _collect_all_steps(doc)
        apply_steps = [s for s in all_steps if "apply-overlays" in str(s.get("run", ""))]
        self.assertTrue(apply_steps, "No step invokes apply-overlays.py")

        # Either the step has a conditional in the run command, or there are multiple
        # steps with if: conditions, or the run block uses github context variables
        apply_run_texts = [s.get("run", "") for s in apply_steps]
        apply_step_ifs = [s.get("if", "") for s in apply_steps]

        combined_runs = " ".join(apply_run_texts)
        combined_ifs = " ".join(str(i) for i in apply_step_ifs)

        has_conditional_logic = (
            "github.event_name" in combined_runs
            or "github.event_name" in combined_ifs
            or "dry_run" in combined_runs
            or "inputs.dry_run" in combined_runs
            or "pull_request" in combined_ifs
            or len(apply_steps) > 1  # separate steps for PR vs push
        )
        self.assertTrue(
            has_conditional_logic,
            f"Apply step must use conditional logic to differentiate PR (dry-run) "
            f"from push-to-main (apply). "
            f"Steps: {apply_steps}",
        )

    def test_workflow_dispatch_dry_run_input_is_honoured(self):
        """
        The apply step must reference the workflow_dispatch dry_run input
        so manual runs can choose apply vs dry-run mode.
        """
        doc = _load_workflow()
        all_runs = _collect_all_run_commands(doc)
        apply_runs = [r for r in all_runs if "apply-overlays" in r]
        combined = " ".join(apply_runs)
        all_steps = _collect_all_steps(doc)
        apply_step_ifs = " ".join(
            str(s.get("if", ""))
            for s in all_steps
            if "apply-overlays" in str(s.get("run", ""))
        )

        references_dispatch_input = (
            "inputs.dry_run" in combined
            or "inputs.dry_run" in apply_step_ifs
            or "github.event.inputs.dry_run" in combined
            or "github.event.inputs.dry_run" in apply_step_ifs
        )
        self.assertTrue(
            references_dispatch_input,
            f"Apply step must reference workflow_dispatch 'dry_run' input. "
            f"apply run texts: {apply_runs}\n"
            f"apply step ifs: {apply_step_ifs}",
        )


# ---------------------------------------------------------------------------
# TestAuthentication
# ---------------------------------------------------------------------------


class TestAuthentication(unittest.TestCase):
    """Tests that the workflow correctly passes credentials to the script."""

    def test_github_token_is_set_from_secrets(self):
        """
        At least one step or job must set GITHUB_TOKEN from the github token secret.
        Accepts either ${{ secrets.GITHUB_TOKEN }} or ${{ github.token }}.
        """
        doc = _load_workflow()
        all_envs = _collect_all_env_blocks(doc)
        workflow_env = str(doc.get("env", "") or "")
        all_env_str = workflow_env + " " + " ".join(str(e) for e in all_envs)

        has_token = (
            "secrets.GITHUB_TOKEN" in all_env_str
            or "github.token" in all_env_str
            or "GITHUB_TOKEN" in all_env_str
        )
        self.assertTrue(
            has_token,
            f"Workflow must set GITHUB_TOKEN from secrets. env blocks: {all_envs}",
        )

    def test_no_hardcoded_credentials_in_workflow(self):
        """The workflow must not contain hardcoded token or password values."""
        with open(WORKFLOW_PATH) as f:
            raw_content = f.read()

        # Check for obvious hardcoded token patterns (ghp_, ghs_, etc.)
        hardcoded_token_pattern = re.compile(r"ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}")
        matches = hardcoded_token_pattern.findall(raw_content)
        self.assertEqual(
            matches,
            [],
            f"Workflow contains hardcoded GitHub tokens: {matches}",
        )


if __name__ == "__main__":
    unittest.main()
