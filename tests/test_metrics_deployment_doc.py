"""Structural tests for the metrics service deployment documentation.

Validates that docs/metrics-deployment.md:
  1. Exists and covers K8s, ECS, and Cloud Run sections
  2. K8s: Deployment YAML with resource limits + liveness/readiness probes,
         Service YAML, Prometheus ServiceMonitor YAML
  3. ECS: Task definition JSON with healthCheck and Secrets Manager references
  4. Cloud Run: gcloud run deploy command with required flags
  5. Environment variables table: PORT, DATABASE_URL, WEBHOOK_SECRET,
         METRICS_AUTH_TOKEN, GITHUB_TOKEN (each with required/optional status)
  6. Secret management: AWS Secrets Manager (ECS), K8s external-secrets,
         Google Secret Manager (Cloud Run)
  7. Prometheus scrape config with bearer_token_file for /metrics auth
  8. Scaling considerations: stateless vs stateful deployment patterns

These are filesystem-only tests — no network access or CLI tools needed.
They FAIL until docs/metrics-deployment.md is created as part of implementation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent
DOC_PATH = REPO_ROOT / "docs" / "metrics-deployment.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_doc() -> str:
    """Return the raw document text, skipping if file does not exist."""
    if not DOC_PATH.exists():
        pytest.skip(
            f"docs/metrics-deployment.md not found at {DOC_PATH}. "
            "Create it with K8s, ECS, and Cloud Run deployment sections."
        )
    return DOC_PATH.read_text()


def _extract_code_blocks(text: str, language: str = "") -> list[str]:
    """Extract fenced code block contents by language from markdown text.

    Handles both lowercase and uppercase language identifiers (yaml/YAML, json/JSON).
    Returns block contents without the fences.
    """
    if language:
        pattern = rf"```{re.escape(language)}\n(.*?)```"
        # Also match uppercase variant
        pattern_upper = rf"```{re.escape(language.upper())}\n(.*?)```"
        return re.findall(pattern, text, re.DOTALL) + re.findall(
            pattern_upper, text, re.DOTALL
        )
    return re.findall(r"```(?:\w*)\n(.*?)```", text, re.DOTALL)


def _extract_section(text: str, *keywords: str) -> str:
    """Extract content under the first heading matching any of the keywords.

    Returns text from the matching heading to the next same-or-higher-level heading.
    If no match is found, returns an empty string.
    """
    for keyword in keywords:
        heading_match = re.search(
            rf"(#{1,6})\s+[^\n]*{re.escape(keyword)}[^\n]*",
            text,
            re.IGNORECASE,
        )
        if heading_match:
            level = len(heading_match.group(1))
            start = heading_match.start()
            end_pattern = rf"(?m)^#{{{1},{level}}}\s"
            next_heading = re.search(end_pattern, text[start + 1 :])
            end = start + 1 + next_heading.start() if next_heading else len(text)
            return text[start:end]
    return ""


def _parse_all_yaml_docs(text: str) -> list[dict[str, Any]]:
    """Extract and parse all YAML code blocks from text, returning valid dicts.

    Handles multi-document YAML blocks (separated by ---).
    Silently ignores blocks that fail to parse.
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed — install pyyaml")
    blocks = _extract_code_blocks(text, "yaml")
    docs: list[dict[str, Any]] = []
    for block in blocks:
        try:
            for doc in yaml.safe_load_all(block):
                if isinstance(doc, dict):
                    docs.append(doc)
        except Exception:
            pass
    return docs


def _parse_all_json_objects(text: str) -> list[Any]:
    """Extract and parse all JSON code blocks from text."""
    blocks = _extract_code_blocks(text, "json")
    objects = []
    for block in blocks:
        try:
            objects.append(json.loads(block))
        except json.JSONDecodeError:
            pass
    return objects


def _k8s_docs_by_kind(text: str, kind: str) -> list[dict[str, Any]]:
    """Return all parsed YAML docs from text whose 'kind' field matches."""
    return [d for d in _parse_all_yaml_docs(text) if d.get("kind") == kind]


def _k8s_containers(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the containers list from a K8s Deployment manifest."""
    return (
        deployment.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


class TestDeploymentDocExists:
    """docs/metrics-deployment.md must exist and have basic structure."""

    def test_doc_file_exists(self):
        """The deployment documentation file must be created in docs/."""
        assert DOC_PATH.exists(), (
            f"docs/metrics-deployment.md not found at {DOC_PATH}. "
            "Create the deployment documentation covering K8s, ECS, and Cloud Run."
        )

    def test_doc_file_is_not_empty(self):
        content = _read_doc()
        assert content.strip(), "docs/metrics-deployment.md must not be empty"

    def test_doc_has_title_heading(self):
        """The document must start with a top-level heading."""
        content = _read_doc()
        h1_lines = [ln for ln in content.splitlines() if ln.startswith("# ")]
        assert h1_lines, (
            "docs/metrics-deployment.md must have a top-level heading (# Title)"
        )

    def test_doc_is_substantial(self):
        """The document must have meaningful content — at least 100 non-empty lines."""
        content = _read_doc()
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) >= 100, (
            f"docs/metrics-deployment.md is too short ({len(lines)} non-empty lines). "
            "A complete deployment guide covering K8s, ECS, Cloud Run, env vars, "
            "secrets, Prometheus scrape config, and scaling should exceed 100 lines."
        )


# ---------------------------------------------------------------------------
# Kubernetes section — Deployment, Service, ServiceMonitor
# ---------------------------------------------------------------------------


class TestKubernetesSection:
    """The Kubernetes section must exist and contain YAML manifests."""

    def test_kubernetes_section_heading_exists(self):
        """A Kubernetes/K8s section heading must be present in the document."""
        content = _read_doc()
        k8s_heading = re.search(
            r"#{1,3}\s+.*(?:[Kk]ubernetes|\bK8s\b)",
            content,
        )
        assert k8s_heading, (
            "docs/metrics-deployment.md must have a Kubernetes (or K8s) section heading. "
            "Example: ## Kubernetes Deployment"
        )

    def test_kubernetes_section_has_yaml_code_blocks(self):
        """The K8s section must contain at least one YAML code block."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        assert k8s_section, "No Kubernetes section found in document"
        yaml_blocks = _extract_code_blocks(k8s_section, "yaml")
        assert yaml_blocks, (
            "The Kubernetes section must include at least one yaml code block "
            "containing deployment manifests."
        )


class TestKubernetesDeploymentManifest:
    """The K8s section must include a valid Deployment manifest."""

    def test_deployment_kind_present(self):
        """A 'kind: Deployment' YAML document must exist in the K8s section."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        assert k8s_section, "No Kubernetes section found in document"
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        assert deployments, (
            "The Kubernetes section must include a 'kind: Deployment' manifest "
            "for the metrics service. "
            "Add a YAML block with apiVersion: apps/v1, kind: Deployment."
        )

    def test_deployment_has_resource_limits(self):
        """Deployment containers must define resource limits (cpu and memory)."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        if not deployments:
            pytest.skip("No Deployment manifest found — covered by test_deployment_kind_present")

        has_limits = any(
            container.get("resources", {}).get("limits")
            for deployment in deployments
            for container in _k8s_containers(deployment)
        )
        assert has_limits, (
            "Deployment containers must define resource limits "
            "(spec.template.spec.containers[].resources.limits). "
            "Without limits, a runaway process can starve other pods on the node. "
            "Example: limits: {cpu: '500m', memory: '256Mi'}"
        )

    def test_deployment_has_resource_requests(self):
        """Deployment containers must define resource requests alongside limits."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        if not deployments:
            pytest.skip("No Deployment manifest found")

        has_requests = any(
            container.get("resources", {}).get("requests")
            for deployment in deployments
            for container in _k8s_containers(deployment)
        )
        assert has_requests, (
            "Deployment containers must define resource requests "
            "(spec.template.spec.containers[].resources.requests). "
            "Requests tell the scheduler how much CPU/memory to reserve per pod. "
            "Example: requests: {cpu: '100m', memory: '128Mi'}"
        )

    def test_deployment_has_liveness_probe(self):
        """Deployment containers must define a livenessProbe."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        if not deployments:
            pytest.skip("No Deployment manifest found")

        has_liveness = any(
            container.get("livenessProbe")
            for deployment in deployments
            for container in _k8s_containers(deployment)
        )
        assert has_liveness, (
            "Deployment containers must define a livenessProbe. "
            "Without it, K8s cannot detect a hung service and restart it. "
            "Example: livenessProbe: {httpGet: {path: /healthz, port: 8000}}"
        )

    def test_deployment_liveness_probe_targets_healthz(self):
        """/healthz must appear in the K8s section as the liveness probe target."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        assert "/healthz" in k8s_section, (
            "The Kubernetes Deployment's livenessProbe must target /healthz. "
            "The kubelet cannot authenticate to /metrics, so /healthz is the "
            "correct probe target (no auth required by design)."
        )

    def test_deployment_has_readiness_probe(self):
        """Deployment containers must define a readinessProbe."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        if not deployments:
            pytest.skip("No Deployment manifest found")

        has_readiness = any(
            container.get("readinessProbe")
            for deployment in deployments
            for container in _k8s_containers(deployment)
        )
        assert has_readiness, (
            "Deployment containers must define a readinessProbe. "
            "Without it, K8s routes traffic before the service is ready, causing "
            "request failures during startup. "
            "Example: readinessProbe: {httpGet: {path: /healthz, port: 8000}}"
        )

    def test_deployment_api_version_is_apps_v1(self):
        """Deployment must use apiVersion: apps/v1 (stable, not beta)."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        deployments = _k8s_docs_by_kind(k8s_section, "Deployment")
        if not deployments:
            pytest.skip("No Deployment manifest found")

        has_stable_api = any(
            deployment.get("apiVersion") == "apps/v1"
            for deployment in deployments
        )
        assert has_stable_api, (
            "Deployment must use apiVersion: apps/v1 (the stable GA API). "
            f"Found apiVersions: {[d.get('apiVersion') for d in deployments]}. "
            "Do not use extensions/v1beta1 or apps/v1beta2 (removed in K8s 1.16+)."
        )


class TestKubernetesServiceManifest:
    """The K8s section must include a Service manifest."""

    def test_service_kind_present(self):
        """A 'kind: Service' YAML document must exist in the K8s section."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        assert k8s_section, "No Kubernetes section found in document"
        services = _k8s_docs_by_kind(k8s_section, "Service")
        assert services, (
            "The Kubernetes section must include a 'kind: Service' manifest "
            "to expose the metrics service within the cluster. "
            "The Service enables Prometheus to discover and scrape the pod."
        )

    def test_service_exposes_metrics_port_8000(self):
        """The Service must expose port 8000 (the metrics FastAPI service port)."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        services = _k8s_docs_by_kind(k8s_section, "Service")
        if not services:
            pytest.skip("No Service manifest found")

        has_port_8000 = any(
            any(
                str(port.get("port")) == "8000"
                or str(port.get("targetPort")) == "8000"
                for port in (svc.get("spec", {}).get("ports") or [])
            )
            for svc in services
        )
        assert has_port_8000, (
            "The Kubernetes Service must expose port 8000 "
            "(the metrics FastAPI service HTTP port). "
            "Example: ports: [{port: 8000, targetPort: 8000}]"
        )


class TestKubernetesServiceMonitorManifest:
    """The K8s section must include a Prometheus Operator ServiceMonitor manifest."""

    def test_service_monitor_kind_present(self):
        """A 'kind: ServiceMonitor' YAML document must exist in the K8s section."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        assert k8s_section, "No Kubernetes section found in document"
        monitors = _k8s_docs_by_kind(k8s_section, "ServiceMonitor")
        assert monitors, (
            "The Kubernetes section must include a 'kind: ServiceMonitor' manifest "
            "for the Prometheus Operator to auto-discover and scrape the metrics service. "
            "Without this, Prometheus requires manual scrape_configs per pod IP."
        )

    def test_service_monitor_uses_monitoring_coreos_api(self):
        """ServiceMonitor must use the monitoring.coreos.com API group."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        monitors = _k8s_docs_by_kind(k8s_section, "ServiceMonitor")
        if not monitors:
            pytest.skip("No ServiceMonitor manifest found")

        has_coreos_api = any(
            "monitoring.coreos.com" in str(m.get("apiVersion", ""))
            for m in monitors
        )
        assert has_coreos_api, (
            "ServiceMonitor must use apiVersion: monitoring.coreos.com/v1 "
            "(the Prometheus Operator CRD API group). "
            f"Found apiVersions: {[m.get('apiVersion') for m in monitors]}"
        )

    def test_service_monitor_references_metrics_path(self):
        """ServiceMonitor must reference the /metrics scrape path."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")
        assert "/metrics" in k8s_section, (
            "The ServiceMonitor manifest must reference /metrics as the scrape path. "
            "Example: endpoints: [{path: /metrics, port: http}]"
        )

    def test_service_monitor_configures_bearer_token_or_auth(self):
        """ServiceMonitor must configure authentication for the /metrics endpoint."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")

        has_auth = (
            "bearerTokenFile" in k8s_section
            or "bearerTokenSecret" in k8s_section
            or "authorization" in k8s_section.lower()
            or "bearer_token" in k8s_section
        )
        assert has_auth, (
            "The ServiceMonitor must configure authentication to scrape /metrics. "
            "The /metrics endpoint requires a bearer token (METRICS_AUTH_TOKEN). "
            "Use: bearerTokenSecret or authorization.credentials in the endpoint spec."
        )


# ---------------------------------------------------------------------------
# ECS section — task definition JSON with health check + Secrets Manager
# ---------------------------------------------------------------------------


class TestECSSection:
    """The ECS section must exist and cover task definition + secret management."""

    def test_ecs_section_heading_exists(self):
        """An ECS section heading must be present in the document."""
        content = _read_doc()
        ecs_heading = re.search(
            r"#{1,3}\s+.*(?:\bECS\b|Elastic Container Service)",
            content,
        )
        assert ecs_heading, (
            "docs/metrics-deployment.md must have an ECS section heading. "
            "Example: ## AWS ECS Deployment"
        )

    def test_ecs_section_has_json_code_block(self):
        """The ECS section must contain a JSON code block (task definition)."""
        content = _read_doc()
        ecs_section = _extract_section(content, "ECS", "Elastic Container Service")
        assert ecs_section, "No ECS section found in document"
        json_blocks = _extract_code_blocks(ecs_section, "json")
        assert json_blocks, (
            "The ECS section must include a JSON code block containing "
            "the ECS task definition for the metrics service."
        )


class TestECSTaskDefinition:
    """The ECS task definition JSON must have all required fields."""

    def _get_ecs_json_objects(self) -> list[Any]:
        content = _read_doc()
        ecs_section = _extract_section(content, "ECS", "Elastic Container Service")
        if not ecs_section:
            pytest.skip("No ECS section found in document")
        objs = _parse_all_json_objects(ecs_section)
        return objs

    def test_task_definition_has_container_definitions(self):
        """ECS task definition must have a 'containerDefinitions' key."""
        json_objs = self._get_ecs_json_objects()
        has_containers = any(
            isinstance(obj, dict) and "containerDefinitions" in obj
            for obj in json_objs
        )
        assert has_containers, (
            "The ECS task definition must include a 'containerDefinitions' key. "
            "This is the required field for specifying container config in ECS tasks."
        )

    def test_task_definition_has_family_field(self):
        """ECS task definition must declare a 'family' name."""
        json_objs = self._get_ecs_json_objects()
        has_family = any(
            isinstance(obj, dict) and "family" in obj
            for obj in json_objs
        )
        assert has_family, (
            "The ECS task definition must declare a 'family' field. "
            "The family name groups revisions together and is referenced by ECS services. "
            "Example: {\"family\": \"gitweave-metrics\"}"
        )

    def test_task_definition_container_has_health_check(self):
        """At least one container in the task definition must define a healthCheck."""
        json_objs = self._get_ecs_json_objects()
        if not json_objs:
            pytest.skip("No JSON objects found in ECS section")

        has_health_check = False
        for obj in json_objs:
            if not isinstance(obj, dict):
                continue
            containers = obj.get("containerDefinitions", [])
            for container in containers:
                if container.get("healthCheck"):
                    has_health_check = True

        assert has_health_check, (
            "The ECS task definition must include a 'healthCheck' for the metrics container. "
            "ECS uses this to replace unhealthy tasks automatically. "
            "Example: {\"healthCheck\": {\"command\": [\"CMD-SHELL\", "
            "\"curl -f http://localhost:8000/healthz || exit 1\"], "
            "\"interval\": 30, \"timeout\": 5, \"retries\": 3}}"
        )

    def test_task_definition_health_check_targets_healthz(self):
        """The ECS healthCheck command must target /healthz."""
        content = _read_doc()
        ecs_section = _extract_section(content, "ECS", "Elastic Container Service")
        if not ecs_section:
            pytest.skip("No ECS section found")
        assert "/healthz" in ecs_section, (
            "The ECS task definition healthCheck must target /healthz. "
            "Example: CMD-SHELL curl -f http://localhost:8000/healthz || exit 1"
        )

    def test_task_definition_uses_secrets_key_for_sensitive_values(self):
        """Container definitions must use the 'secrets' key for Secrets Manager values."""
        json_objs = self._get_ecs_json_objects()
        if not json_objs:
            pytest.skip("No JSON objects found in ECS section")

        has_secrets_key = False
        for obj in json_objs:
            if not isinstance(obj, dict):
                continue
            containers = obj.get("containerDefinitions", [])
            for container in containers:
                if container.get("secrets"):
                    has_secrets_key = True

        assert has_secrets_key, (
            "ECS container definitions must use the 'secrets' key to inject values "
            "from AWS Secrets Manager. The 'secrets' key (not 'environment') is the "
            "correct ECS mechanism for secret injection. "
            "Example: {\"secrets\": [{\"name\": \"WEBHOOK_SECRET\", "
            "\"valueFrom\": \"arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:gitweave/webhook-secret\"}]}"
        )

    def test_task_definition_secrets_reference_secretsmanager_arn(self):
        """Secrets in the task definition must reference Secrets Manager ARNs."""
        content = _read_doc()
        ecs_section = _extract_section(content, "ECS", "Elastic Container Service")
        if not ecs_section:
            pytest.skip("No ECS section found")

        has_sm_reference = (
            "secretsmanager" in ecs_section.lower()
            or "arn:aws" in ecs_section.lower()
            or "Secrets Manager" in ecs_section
        )
        assert has_sm_reference, (
            "The ECS task definition secrets must reference AWS Secrets Manager ARNs. "
            "Example valueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:NAME"
        )


# ---------------------------------------------------------------------------
# Cloud Run section — gcloud run deploy command with required flags
# ---------------------------------------------------------------------------


class TestCloudRunSection:
    """The Cloud Run section must exist and cover the deployment command."""

    def test_cloud_run_section_heading_exists(self):
        """A Cloud Run section heading must be present in the document."""
        content = _read_doc()
        cr_heading = re.search(
            r"#{1,3}\s+.*(?:Cloud Run|GCP|Google Cloud)",
            content,
        )
        assert cr_heading, (
            "docs/metrics-deployment.md must have a Cloud Run section heading. "
            "Example: ## Google Cloud Run Deployment"
        )

    def test_cloud_run_section_has_gcloud_command(self):
        """The Cloud Run section must include a gcloud run deploy command."""
        content = _read_doc()
        cr_section = _extract_section(content, "Cloud Run", "GCP", "Google Cloud")
        assert cr_section, "No Cloud Run section found in document"
        assert "gcloud run deploy" in cr_section, (
            "The Cloud Run section must include a 'gcloud run deploy' command. "
            "This is the standard CLI command for deploying services to Cloud Run."
        )


class TestCloudRunDeployCommand:
    """The gcloud run deploy command must include all required flags."""

    def _get_cr_section(self) -> str:
        content = _read_doc()
        section = _extract_section(content, "Cloud Run", "GCP", "Google Cloud")
        if not section:
            pytest.skip("No Cloud Run section found in document")
        return section

    def test_command_has_image_flag(self):
        """gcloud run deploy must include --image to specify the container image."""
        section = self._get_cr_section()
        assert "--image" in section, (
            "The gcloud run deploy command must include --image <image-url> "
            "to specify which container image to deploy to Cloud Run."
        )

    def test_command_has_port_flag(self):
        """gcloud run deploy must include --port to specify the service port."""
        section = self._get_cr_section()
        assert "--port" in section, (
            "The gcloud run deploy command must include --port 8000 "
            "to tell Cloud Run which port the metrics service listens on."
        )

    def test_command_has_region_flag(self):
        """gcloud run deploy must include --region to specify the deployment region."""
        section = self._get_cr_section()
        assert "--region" in section, (
            "The gcloud run deploy command must include --region "
            "to specify the Cloud Run region (e.g., --region us-central1)."
        )

    def test_command_has_platform_flag(self):
        """gcloud run deploy must include --platform managed."""
        section = self._get_cr_section()
        assert "--platform" in section, (
            "The gcloud run deploy command must include --platform managed "
            "to explicitly target the fully-managed Cloud Run service "
            "(as opposed to Cloud Run for Anthos)."
        )

    def test_command_sets_environment_variables_or_secrets(self):
        """The Cloud Run deploy command must set env vars or secrets."""
        section = self._get_cr_section()
        has_env_or_secrets = (
            "--set-env-vars" in section
            or "--set-secrets" in section
            or "--update-env-vars" in section
            or "--update-secrets" in section
        )
        assert has_env_or_secrets, (
            "The gcloud run deploy command must set environment variables or secrets "
            "using --set-env-vars or --set-secrets flags. "
            "Sensitive values should use --set-secrets to reference Google Secret Manager. "
            "Example: --set-secrets=WEBHOOK_SECRET=webhook-secret:latest"
        )

    def test_command_references_service_name(self):
        """The gcloud run deploy command must specify the service name."""
        section = self._get_cr_section()
        assert "gcloud run deploy gitweave-metrics" in section or (
            "gcloud run deploy" in section and "metrics" in section
        ), (
            "The gcloud run deploy command must specify the service name. "
            "Example: gcloud run deploy gitweave-metrics --image ..."
        )


# ---------------------------------------------------------------------------
# Environment variables table
# ---------------------------------------------------------------------------


REQUIRED_ENV_VARS = [
    "PORT",
    "DATABASE_URL",
    "WEBHOOK_SECRET",
    "METRICS_AUTH_TOKEN",
    "GITHUB_TOKEN",
]


class TestEnvironmentVariablesTable:
    """The document must contain a table documenting all required env vars."""

    def test_environment_variables_section_exists(self):
        """An Environment Variables section must exist in the document."""
        content = _read_doc()
        env_section = re.search(
            r"#{1,3}\s+.*(?:[Ee]nvironment [Vv]ariable|[Ee]nv [Vv]ar|Configuration)",
            content,
        )
        assert env_section, (
            "docs/metrics-deployment.md must include an Environment Variables section. "
            "Example: ## Environment Variables"
        )

    @pytest.mark.parametrize("env_var", REQUIRED_ENV_VARS)
    def test_env_var_is_documented(self, env_var: str):
        """Each required environment variable must appear in the document."""
        content = _read_doc()
        assert env_var in content, (
            f"Environment variable '{env_var}' must be documented in "
            "docs/metrics-deployment.md. Include it in an environment variables table "
            "with a description and required/optional status."
        )

    def test_env_vars_table_uses_markdown_table_format(self):
        """The env vars section must use a markdown table with pipe characters."""
        content = _read_doc()
        env_section = _extract_section(
            content, "Environment Variable", "Env Var", "Configuration"
        )
        if not env_section:
            pytest.skip("No Environment Variables section found")

        # A markdown table has pipe characters in multiple lines
        table_lines = [ln for ln in env_section.splitlines() if "|" in ln]
        assert len(table_lines) >= 3, (
            "The environment variables section should use a markdown table (| delimited). "
            "Expected at least 3 table lines (header, separator, data rows)."
        )

    def test_env_vars_have_required_optional_status(self):
        """The env vars table must indicate which variables are required vs optional."""
        content = _read_doc()
        env_section = _extract_section(
            content, "Environment Variable", "Env Var", "Configuration"
        )
        if not env_section:
            pytest.skip("No Environment Variables section found")

        has_status = (
            "required" in env_section.lower() or "optional" in env_section.lower()
        )
        assert has_status, (
            "The environment variables section must indicate which variables are "
            "'Required' or 'Optional'. This helps operators know which variables "
            "must be set for the service to start successfully."
        )

    def test_port_env_var_documents_default_value(self):
        """PORT must document its default value of 8000."""
        content = _read_doc()
        port_idx = content.find("PORT")
        assert port_idx != -1, "PORT must be documented"
        context = content[max(0, port_idx - 50) : port_idx + 200]
        assert "8000" in context, (
            "PORT environment variable documentation must mention the default "
            "value of 8000 (the FastAPI service listen port)."
        )

    def test_database_url_env_var_mentions_postgresql(self):
        """DATABASE_URL documentation must mention PostgreSQL or connection string."""
        content = _read_doc()
        db_url_idx = content.find("DATABASE_URL")
        assert db_url_idx != -1, "DATABASE_URL must be documented"
        context = content[max(0, db_url_idx - 100) : db_url_idx + 300]
        has_pg_context = any(
            kw in context.lower()
            for kw in ["postgres", "postgresql", "connection string", "database"]
        )
        assert has_pg_context, (
            "DATABASE_URL documentation must describe it as the PostgreSQL connection "
            "string. Example: postgresql://user:pass@host:5432/gitweave"
        )

    def test_webhook_secret_env_var_is_marked_required(self):
        """WEBHOOK_SECRET must be marked as required (not optional)."""
        content = _read_doc()
        ws_idx = content.find("WEBHOOK_SECRET")
        assert ws_idx != -1, "WEBHOOK_SECRET must be documented"
        # Check the surrounding context (same table row) for 'required'
        row_context = content[max(0, ws_idx - 50) : ws_idx + 200]
        assert "required" in row_context.lower() or "Required" in row_context, (
            "WEBHOOK_SECRET must be marked as Required. "
            "Without it, GitHub webhook signature verification fails."
        )

    def test_metrics_auth_token_env_var_is_documented(self):
        """METRICS_AUTH_TOKEN must be documented with a description."""
        content = _read_doc()
        token_idx = content.find("METRICS_AUTH_TOKEN")
        assert token_idx != -1, "METRICS_AUTH_TOKEN must be documented"
        context = content[max(0, token_idx - 100) : token_idx + 300]
        has_auth_context = any(
            kw in context.lower()
            for kw in ["bearer", "prometheus", "auth", "protect", "scrape"]
        )
        assert has_auth_context, (
            "METRICS_AUTH_TOKEN documentation must describe its purpose "
            "(protecting the /metrics endpoint from unauthenticated Prometheus scrapes)."
        )

    def test_github_token_env_var_is_marked_optional(self):
        """GITHUB_TOKEN must be documented; it should indicate optional status."""
        content = _read_doc()
        assert "GITHUB_TOKEN" in content, "GITHUB_TOKEN must be documented"
        gt_idx = content.find("GITHUB_TOKEN")
        context = content[max(0, gt_idx - 50) : gt_idx + 300]
        # GITHUB_TOKEN is used for API calls but may be optional if no API calls are made
        has_status = (
            "optional" in context.lower()
            or "required" in context.lower()
            or "Optional" in context
            or "Required" in context
        )
        assert has_status, (
            "GITHUB_TOKEN documentation must indicate whether it is Required or Optional."
        )


# ---------------------------------------------------------------------------
# Secret management per platform
# ---------------------------------------------------------------------------


class TestSecretManagement:
    """The document must cover platform-specific secret management."""

    def test_secret_management_coverage_exists(self):
        """The document must address secret management for all three platforms."""
        content = _read_doc()
        has_secrets_coverage = "secret" in content.lower() and any(
            kw in content
            for kw in [
                "Secrets Manager",
                "secretsmanager",
                "Secret Manager",
                "external-secrets",
                "secretKeyRef",
            ]
        )
        assert has_secrets_coverage, (
            "docs/metrics-deployment.md must document secret management. "
            "Cover AWS Secrets Manager (ECS), K8s external-secrets or K8s Secrets, "
            "and Google Secret Manager (Cloud Run)."
        )

    def test_aws_secrets_manager_documented_in_ecs_section(self):
        """AWS Secrets Manager must be documented in the ECS section."""
        content = _read_doc()
        ecs_section = _extract_section(content, "ECS", "Elastic Container Service")
        if not ecs_section:
            pytest.skip("No ECS section found")

        has_aws_sm = (
            "Secrets Manager" in ecs_section
            or "secretsmanager" in ecs_section.lower()
            or "aws:secretsmanager" in ecs_section.lower()
        )
        assert has_aws_sm, (
            "The ECS section must document AWS Secrets Manager for secret injection. "
            "ECS tasks should reference Secrets Manager ARNs via the 'secrets' key "
            "in containerDefinitions, not hardcode secrets in 'environment'."
        )

    def test_kubernetes_secret_management_documented(self):
        """K8s secret management (external-secrets or native Secrets) must be documented."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")

        has_k8s_secrets = (
            "external-secrets" in k8s_section.lower()
            or "ExternalSecret" in k8s_section
            or "kind: Secret" in k8s_section
            or "secretKeyRef" in k8s_section
            or "Kubernetes Secret" in k8s_section
        )
        assert has_k8s_secrets, (
            "The Kubernetes section must document how secrets are managed. "
            "Prefer external-secrets operator (syncs from AWS SM/GCP SM/Vault) "
            "over native K8s Secrets for production workloads to avoid committing "
            "base64-encoded values to git."
        )

    def test_external_secrets_operator_referenced_for_k8s(self):
        """The K8s section should reference external-secrets for production secret sync."""
        content = _read_doc()
        k8s_section = _extract_section(content, "Kubernetes", "K8s")
        if not k8s_section:
            pytest.skip("No Kubernetes section found")

        has_external_secrets = (
            "external-secrets" in k8s_section.lower()
            or "ExternalSecret" in k8s_section
            or "external_secrets" in k8s_section.lower()
        )
        assert has_external_secrets, (
            "The Kubernetes secret management section should reference the "
            "external-secrets operator (kubernetes-sigs/external-secrets). "
            "This is the recommended approach for syncing secrets from AWS SM, "
            "GCP SM, or HashiCorp Vault into K8s Secrets."
        )

    def test_google_secret_manager_documented_in_cloud_run_section(self):
        """Google Secret Manager must be documented in the Cloud Run section."""
        content = _read_doc()
        cr_section = _extract_section(content, "Cloud Run", "GCP", "Google Cloud")
        if not cr_section:
            pytest.skip("No Cloud Run section found")

        has_gsm = (
            "Secret Manager" in cr_section
            or "secret-manager" in cr_section.lower()
            or "--set-secrets" in cr_section
            or "google secret" in cr_section.lower()
        )
        assert has_gsm, (
            "The Cloud Run section must document Google Secret Manager for secret injection. "
            "Use --set-secrets flag in gcloud run deploy to reference GSM secrets. "
            "Example: --set-secrets=WEBHOOK_SECRET=projects/PROJECT/secrets/webhook-secret:latest"
        )


# ---------------------------------------------------------------------------
# Prometheus scrape config
# ---------------------------------------------------------------------------


class TestPrometheusScrapeConfig:
    """The document must include a Prometheus scrape configuration block."""

    def test_prometheus_content_exists_in_document(self):
        """Prometheus scrape configuration must be mentioned in the document."""
        content = _read_doc()
        assert "prometheus" in content.lower(), (
            "docs/metrics-deployment.md must cover Prometheus scrape configuration. "
            "Include a scrape_configs section showing how Prometheus discovers and "
            "authenticates to the /metrics endpoint."
        )

    def test_prometheus_scrape_config_yaml_block_present(self):
        """A YAML block containing Prometheus scrape_configs must be present."""
        content = _read_doc()
        yaml_blocks = _extract_code_blocks(content, "yaml")
        has_scrape_config = any(
            "scrape_configs" in block or "job_name" in block
            for block in yaml_blocks
        )
        assert has_scrape_config, (
            "docs/metrics-deployment.md must include a yaml code block showing "
            "the Prometheus scrape_configs entry for the metrics service. "
            "Include job_name, static_configs or service_discovery, and auth config."
        )

    def test_prometheus_scrape_config_has_bearer_token_auth(self):
        """The Prometheus scrape config must configure bearer token authentication."""
        content = _read_doc()
        yaml_blocks = _extract_code_blocks(content, "yaml")
        has_bearer_token = any(
            "bearer_token_file" in block or "bearer_token" in block
            for block in yaml_blocks
        )
        assert has_bearer_token, (
            "The Prometheus scrape config must include bearer_token_file "
            "(or bearer_token) to authenticate to the /metrics endpoint. "
            "The metrics service requires METRICS_AUTH_TOKEN for /metrics access. "
            "Example: bearer_token_file: /var/run/secrets/metrics-token"
        )

    def test_prometheus_scrape_config_has_job_name(self):
        """The Prometheus scrape config must define a job_name."""
        content = _read_doc()
        yaml_blocks = _extract_code_blocks(content, "yaml")
        scrape_blocks = [
            b for b in yaml_blocks if "scrape_configs" in b or "job_name" in b
        ]
        if not scrape_blocks:
            pytest.skip("No Prometheus scrape config block found")

        scrape_text = " ".join(scrape_blocks)
        assert "job_name" in scrape_text, (
            "The Prometheus scrape config must define a job_name for the metrics service. "
            "Example: job_name: gitweave-metrics"
        )

    def test_prometheus_scrape_config_targets_metrics_path(self):
        """The Prometheus scrape config must target the /metrics path."""
        content = _read_doc()
        yaml_blocks = _extract_code_blocks(content, "yaml")
        scrape_blocks = [
            b for b in yaml_blocks if "scrape_configs" in b or "job_name" in b
        ]
        if not scrape_blocks:
            pytest.skip("No Prometheus scrape config block found")

        scrape_text = " ".join(scrape_blocks)
        # /metrics is the default path but should be explicitly specified
        assert "/metrics" in scrape_text or "metrics_path" in scrape_text, (
            "The Prometheus scrape config should explicitly specify /metrics as "
            "the metrics_path. While /metrics is the Prometheus default, "
            "explicit configuration makes the intent clear."
        )


# ---------------------------------------------------------------------------
# Scaling considerations
# ---------------------------------------------------------------------------


class TestScalingConsiderations:
    """The document must cover stateless and stateful scaling patterns."""

    def test_scaling_section_exists(self):
        """A Scaling section must be present in the document."""
        content = _read_doc()
        has_scaling = re.search(
            r"#{1,3}\s+.*(?:[Ss]caling|[Ss]cale)",
            content,
        )
        assert has_scaling, (
            "docs/metrics-deployment.md must include a Scaling section. "
            "Example: ## Scaling Considerations"
        )

    def test_stateless_deployment_pattern_documented(self):
        """The document must describe the stateless deployment pattern (in-memory only)."""
        content = _read_doc()
        assert "stateless" in content.lower(), (
            "The document must describe the stateless deployment pattern. "
            "Stateless mode uses InMemoryEventStore (no PostgreSQL), can scale "
            "horizontally without coordination, but loses events on pod restart."
        )

    def test_stateful_deployment_pattern_documented(self):
        """The document must describe the stateful deployment pattern (with PostgreSQL)."""
        content = _read_doc()
        has_stateful = "stateful" in content.lower() or (
            "postgresql" in content.lower() and "persist" in content.lower()
        )
        assert has_stateful, (
            "The document must describe the stateful deployment pattern with PostgreSQL. "
            "Stateful mode persists events to PostgreSQL, enabling multi-replica "
            "deployments and event retention across restarts. Requires DATABASE_URL."
        )

    def test_stateless_pattern_notes_in_memory_trade_off(self):
        """The stateless section must clarify the in-memory trade-off."""
        content = _read_doc()
        has_memory_note = (
            "in-memory" in content.lower()
            or "in memory" in content.lower()
            or ("stateless" in content.lower() and "loss" in content.lower())
            or ("stateless" in content.lower() and "restart" in content.lower())
        )
        assert has_memory_note, (
            "The stateless pattern description must clarify that events are held "
            "in memory only and lost on pod/container restart. "
            "This trade-off is important for operators choosing between modes."
        )

    def test_stateful_pattern_references_database_url(self):
        """The stateful section must reference DATABASE_URL as the activation mechanism."""
        content = _read_doc()
        has_pg_requirement = "DATABASE_URL" in content and (
            "postgres" in content.lower() or "postgresql" in content.lower()
        )
        assert has_pg_requirement, (
            "The stateful deployment section must mention DATABASE_URL and PostgreSQL. "
            "Setting DATABASE_URL activates PostgreSQLEventStore (stateful mode). "
            "Without it, the service defaults to InMemoryEventStore (stateless mode)."
        )

    def test_scaling_section_covers_both_patterns(self):
        """The Scaling section must address both stateless and stateful patterns."""
        content = _read_doc()
        scaling_section = _extract_section(content, "Scaling")
        if not scaling_section:
            # Fall back to full document if no dedicated section
            scaling_section = content

        has_both = (
            "stateless" in scaling_section.lower()
            and ("stateful" in scaling_section.lower() or "postgresql" in scaling_section.lower())
        )
        assert has_both, (
            "The scaling section must cover both the stateless (in-memory) and "
            "stateful (PostgreSQL) deployment patterns. "
            "Operators need to understand when to use each mode."
        )


# ---------------------------------------------------------------------------
# Cross-cutting — all platforms referenced
# ---------------------------------------------------------------------------


class TestAllPlatformsCovered:
    """All three deployment target platforms must be covered in the document."""

    def test_kubernetes_covered(self):
        """Kubernetes must be mentioned as a deployment target."""
        content = _read_doc()
        assert "kubernetes" in content.lower() or "K8s" in content, (
            "docs/metrics-deployment.md must cover Kubernetes deployment."
        )

    def test_ecs_covered(self):
        """AWS ECS must be mentioned as a deployment target."""
        content = _read_doc()
        assert "ECS" in content or "Elastic Container Service" in content, (
            "docs/metrics-deployment.md must cover AWS ECS deployment."
        )

    def test_cloud_run_covered(self):
        """Google Cloud Run must be mentioned as a deployment target."""
        content = _read_doc()
        assert "Cloud Run" in content, (
            "docs/metrics-deployment.md must cover Google Cloud Run deployment."
        )

    def test_all_five_env_vars_documented_together(self):
        """All five required env vars must appear in the same document."""
        content = _read_doc()
        missing = [ev for ev in REQUIRED_ENV_VARS if ev not in content]
        assert not missing, (
            f"The following required environment variables are not documented: {missing}. "
            "All five (PORT, DATABASE_URL, WEBHOOK_SECRET, METRICS_AUTH_TOKEN, "
            "GITHUB_TOKEN) must appear in docs/metrics-deployment.md."
        )
