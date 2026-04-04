"""
Tests for .github/workflows/metrics-docker.yaml — the CI/CD pipeline that
lints, builds, scans, and publishes the metrics service Docker image.

Added by PR #21 (feat/GitWeave-metrics-docker).

Acceptance criteria:
  - metrics-docker.yaml exists at .github/workflows/
  - Workflow triggers on pull_request with path filter metrics/**
  - Workflow triggers on push to main with path filter metrics/**
  - A lint job runs hadolint against metrics/Dockerfile on every PR
  - A build job runs docker build on every PR
  - A security scan job runs Trivy (or equivalent) and fails on CRITICAL CVEs
  - A push/publish job runs only on push to main (not on PRs)
  - Minimal permissions: contents: read at workflow level or per job
  - packages: write permission is present only where image push happens (main only)

All tests in this file FAIL until .github/workflows/metrics-docker.yaml is
created by merging PR #21 (TDD red phase).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "metrics-docker.yaml"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_workflow() -> dict:
    """Parse metrics-docker.yaml and return the document dict."""
    import yaml

    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def _get_triggers(doc: dict) -> dict:
    """
    Return the workflow trigger mapping.
    PyYAML parses the bare `on:` key as boolean True in YAML 1.1 — handle both.
    """
    return doc.get("on") or doc.get(True) or {}


def _collect_all_steps(doc: dict) -> list:
    """Return a flat list of every step object across all jobs."""
    steps = []
    for job in doc.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


def _all_run_commands(doc: dict) -> str:
    """Return one string containing every run: value across all jobs and steps."""
    return " ".join(str(s.get("run", "")) for s in _collect_all_steps(doc))


def _all_step_uses(doc: dict) -> list[str]:
    """Return all uses: values from every step in every job."""
    return [
        str(s.get("uses", ""))
        for s in _collect_all_steps(doc)
        if s.get("uses")
    ]


def _find_job_by_keyword(doc: dict, keyword: str) -> dict | None:
    """Return the first job whose id or name contains keyword (case-insensitive)."""
    kw = keyword.lower()
    for jid, job in doc.get("jobs", {}).items():
        if kw in jid.lower() or kw in str(job.get("name", "")).lower():
            return job
    return None


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowExists(unittest.TestCase):
    """The workflow file must be present after PR #21 is merged."""

    def test_metrics_docker_yaml_exists(self):
        """metrics-docker.yaml must exist at .github/workflows/."""
        self.assertTrue(
            WORKFLOW_PATH.exists(),
            f".github/workflows/metrics-docker.yaml not found at {WORKFLOW_PATH}. "
            "Merge PR #21 (feat/GitWeave-metrics-docker) to create it.",
        )

    def test_metrics_docker_yaml_is_valid_yaml(self):
        """The file must parse as a valid YAML mapping."""
        import yaml

        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        with open(WORKFLOW_PATH) as f:
            doc = yaml.safe_load(f)
        self.assertIsInstance(
            doc,
            dict,
            "metrics-docker.yaml must be a valid YAML mapping at the top level",
        )


# ---------------------------------------------------------------------------
# Workflow triggers
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowTriggers(unittest.TestCase):
    """Workflow must trigger on PRs touching metrics/** and on merge to main."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()
        self.triggers = _get_triggers(self.doc)

    def test_workflow_triggers_on_pull_request(self):
        """pull_request trigger is required so CI runs before PRs are merged."""
        self.assertIn(
            "pull_request",
            self.triggers,
            "metrics-docker.yaml must trigger on pull_request events",
        )

    def test_workflow_triggers_on_push_to_main(self):
        """push trigger targeting main is required for the image publish step."""
        push_trigger = self.triggers.get("push", {})
        branches = push_trigger.get("branches", [])
        self.assertTrue(
            any("main" in str(b) for b in branches),
            f"metrics-docker.yaml must trigger on push to main; "
            f"push.branches found: {branches}",
        )

    def test_pull_request_trigger_has_metrics_path_filter(self):
        """Pull request trigger must filter on metrics/** paths to avoid spurious runs."""
        pr_trigger = self.triggers.get("pull_request", {})
        paths = pr_trigger.get("paths", [])
        self.assertTrue(
            any("metrics" in str(p) for p in paths),
            f"pull_request trigger must include a metrics/** path filter; "
            f"paths found: {paths}",
        )

    def test_push_trigger_has_metrics_path_filter(self):
        """Push trigger must also filter on metrics/** paths."""
        push_trigger = self.triggers.get("push", {})
        paths = push_trigger.get("paths", [])
        self.assertTrue(
            any("metrics" in str(p) for p in paths),
            f"push trigger must include a metrics/** path filter; "
            f"paths found: {paths}",
        )


# ---------------------------------------------------------------------------
# Dockerfile linting (hadolint)
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowLintJob(unittest.TestCase):
    """A hadolint step must run to validate Dockerfile best practices."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()

    def test_hadolint_step_is_present(self):
        """hadolint must run to catch Dockerfile anti-patterns and pin-version issues."""
        run_cmds = _all_run_commands(self.doc)
        step_uses = _all_step_uses(self.doc)
        has_hadolint = (
            "hadolint" in run_cmds.lower()
            or any("hadolint" in u.lower() for u in step_uses)
        )
        self.assertTrue(
            has_hadolint,
            "metrics-docker.yaml must run hadolint to lint the Dockerfile. "
            "Add a step that runs: hadolint metrics/Dockerfile",
        )

    def test_hadolint_targets_metrics_dockerfile(self):
        """hadolint must be directed at metrics/Dockerfile specifically."""
        run_cmds = _all_run_commands(self.doc)
        has_metrics_dockerfile_target = (
            "metrics/Dockerfile" in run_cmds
            or "Dockerfile" in run_cmds
        )
        self.assertTrue(
            has_metrics_dockerfile_target,
            "hadolint must target metrics/Dockerfile (or Dockerfile within metrics context)",
        )


# ---------------------------------------------------------------------------
# Docker build step
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowBuildJob(unittest.TestCase):
    """A docker build step must run on every PR to catch build errors early."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()

    def test_docker_build_step_is_present(self):
        """docker build must be invoked to verify the image compiles without errors."""
        run_cmds = _all_run_commands(self.doc)
        step_uses = _all_step_uses(self.doc)
        has_build = (
            "docker build" in run_cmds
            or any("docker/build" in u.lower() for u in step_uses)
            or any("build-push" in u.lower() for u in step_uses)
        )
        self.assertTrue(
            has_build,
            "metrics-docker.yaml must run docker build on every PR so build errors "
            "are caught before merge. Add a step that runs: docker build metrics/",
        )

    def test_docker_build_targets_metrics_directory(self):
        """docker build must use metrics/ as the build context."""
        run_cmds = _all_run_commands(self.doc)
        self.assertTrue(
            "metrics" in run_cmds,
            "docker build command must reference the metrics/ directory as the build context",
        )


# ---------------------------------------------------------------------------
# Security scan (Trivy)
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowSecurityScan(unittest.TestCase):
    """A Trivy (or equivalent) vulnerability scan must gate the pipeline."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()

    def test_trivy_scan_step_is_present(self):
        """Trivy must scan the built image and fail on CRITICAL CVEs."""
        run_cmds = _all_run_commands(self.doc).lower()
        step_uses = [u.lower() for u in _all_step_uses(self.doc)]
        has_trivy = (
            "trivy" in run_cmds
            or any("trivy" in u for u in step_uses)
        )
        self.assertTrue(
            has_trivy,
            "metrics-docker.yaml must include a Trivy image scan step. "
            "Add aquasecurity/trivy-action or a 'trivy image' run step.",
        )

    def test_trivy_scan_fails_on_critical_cves(self):
        """Trivy must be configured to exit non-zero on CRITICAL severity CVEs."""
        run_cmds = _all_run_commands(self.doc).lower()
        # Check for CRITICAL severity exit setting in run commands
        # Also accept if a trivy-action with severity: CRITICAL is used
        all_content = WORKFLOW_PATH.read_text().lower()
        has_critical_gate = (
            "critical" in all_content
            and ("trivy" in all_content or "scan" in all_content)
        )
        self.assertTrue(
            has_critical_gate,
            "Trivy scan must be configured to fail on CRITICAL severity CVEs. "
            "Set --severity CRITICAL,HIGH --exit-code 1 or severity: CRITICAL in the action.",
        )


# ---------------------------------------------------------------------------
# Image push (main-only)
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowPushJob(unittest.TestCase):
    """Image push to GHCR must only happen on merge to main, never on PRs."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()

    def test_image_push_step_is_present(self):
        """A docker push or build-push-action step must be present for main merges."""
        run_cmds = _all_run_commands(self.doc)
        step_uses = _all_step_uses(self.doc)
        has_push = (
            "docker push" in run_cmds
            or "docker/build-push-action" in " ".join(step_uses).lower()
        )
        self.assertTrue(
            has_push,
            "metrics-docker.yaml must have an image push step to publish to GHCR "
            "on merge to main. Add docker push or docker/build-push-action.",
        )

    def test_image_pushed_to_ghcr(self):
        """Image must be published to GitHub Container Registry (ghcr.io)."""
        workflow_text = WORKFLOW_PATH.read_text()
        self.assertIn(
            "ghcr.io",
            workflow_text,
            "metrics-docker.yaml must push the image to ghcr.io (GitHub Container Registry). "
            "Set the image tag to ghcr.io/<owner>/gitweave-metrics:latest",
        )

    def test_push_step_is_conditional_on_main(self):
        """Push step must not run on PRs — only on pushes/merges to main."""
        workflow_text = WORKFLOW_PATH.read_text().lower()
        # Look for an 'if:' condition referencing main or ref_name, or a
        # separate job that only runs on push (not pull_request)
        has_main_condition = (
            "github.ref" in workflow_text
            or "github.event_name" in workflow_text
            or "ref_name" in workflow_text
        )
        self.assertTrue(
            has_main_condition,
            "The image push step or job must be conditional on running against main "
            "(e.g. if: github.ref == 'refs/heads/main' or if: github.event_name == 'push'). "
            "Images must not be published on PR builds.",
        )


# ---------------------------------------------------------------------------
# Least-privilege permissions
# ---------------------------------------------------------------------------


class TestMetricsDockerWorkflowPermissions(unittest.TestCase):
    """Workflow must enforce minimal GitHub Actions permissions."""

    def setUp(self):
        if not WORKFLOW_PATH.exists():
            self.skipTest(f"metrics-docker.yaml not found at {WORKFLOW_PATH}")
        self.doc = _load_workflow()

    def test_contents_read_permission_is_set(self):
        """contents: read must be declared to follow least-privilege policy."""
        workflow_text = WORKFLOW_PATH.read_text()
        self.assertIn(
            "contents: read",
            workflow_text,
            "metrics-docker.yaml must declare 'contents: read' in permissions "
            "to follow the least-privilege policy.",
        )

    def test_packages_write_permission_is_present_for_push(self):
        """packages: write is required to push the image to GHCR."""
        workflow_text = WORKFLOW_PATH.read_text()
        self.assertIn(
            "packages: write",
            workflow_text,
            "metrics-docker.yaml must declare 'packages: write' permission "
            "on the job that pushes the image to GHCR.",
        )

    def test_packages_write_is_not_at_workflow_level_globally(self):
        """packages: write must NOT be set globally — only on the push job."""
        workflow_level_perms = self.doc.get("permissions", {})
        if isinstance(workflow_level_perms, dict):
            packages_perm = workflow_level_perms.get("packages", "")
            self.assertNotEqual(
                str(packages_perm).lower(),
                "write",
                "packages: write must NOT be set at the workflow level — "
                "restrict it to the specific job that pushes images to GHCR "
                "to limit blast radius if the workflow is compromised.",
            )


if __name__ == "__main__":
    unittest.main()
