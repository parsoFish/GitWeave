"""Integration tests: synthetic GitHub webhook events validate all four DORA metrics.

Sends synthetic GitHub webhook payloads to a FastAPI TestClient and validates
that all four DORA metrics are correctly computed and exposed in Prometheus
exposition format via GET /metrics.

Test architecture:
- FastAPI TestClient provides a real HTTP request/response cycle (no network socket)
- Fresh InMemoryEventStore injected per test via FastAPI dependency_overrides
- Events posted to POST /webhook as valid GitHub-format JSON with HMAC-SHA256 signatures
- GET /metrics response parsed to extract metric values and label sets
- All assertions verify both the metric value AND the expected label set

DORA Metrics under test:
- Deployment Frequency : successful deployments per day (30-day rolling window)
- Lead Time for Changes: push-to-successful-deployment duration in hours
- Change Failure Rate  : fraction of deployments that ended in failure
- Mean Time to Restore : hours from a failure event to its recovery deployment

Note: These tests define the expected behaviour and will FAIL until the DORA
metric calculators and Prometheus exposition are implemented in the FastAPI app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

# Ensure src/ is importable regardless of how pytest is invoked
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "test-dora-integration-secret-secure!!"
REPO = "org/gitweave-test-repo"
ENVIRONMENT = "production"

# Prometheus metric names the implementation must expose
METRIC_DEPLOYMENT_FREQUENCY = "gitweave_deployment_frequency_daily"
METRIC_LEAD_TIME = "gitweave_lead_time_for_changes_hours"
METRIC_CFR = "gitweave_change_failure_rate"
METRIC_MTTR = "gitweave_mean_time_to_restore_hours"

# Anchored reference time — computed once so all events in a session share
# a common origin point relative to real wall-clock time.  This ensures events
# injected in tests fall within the implementation's rolling time windows.
_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Format a timezone-aware datetime as a GitHub-style ISO-8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_signature(body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature used by GitHub webhook deliveries."""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def _post_webhook(
    client: Any,
    event_type: str,
    payload: dict[str, Any],
    *,
    secret: str = WEBHOOK_SECRET,
) -> Any:
    """POST a webhook event payload with a valid HMAC-SHA256 signature header.

    Mirrors what GitHub sends on every delivery — the signature header lets
    the receiver verify authenticity before processing the payload.
    """
    body = json.dumps(payload).encode("utf-8")
    sig = _compute_signature(body, secret)
    return client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": event_type,
            "X-Hub-Signature-256": sig,
            "Content-Type": "application/json",
        },
    )


def _make_deployment_status_payload(
    repo: str,
    state: str,
    environment: str,
    created_at: datetime,
    deployment_id: int = 1,
) -> dict[str, Any]:
    """Build a minimal but schema-valid GitHub deployment_status webhook payload."""
    return {
        "deployment_status": {
            "id": deployment_id,
            "state": state,
            "environment": environment,
            "created_at": _iso(created_at),
        },
        "repository": {"full_name": repo},
    }


def _make_push_payload(
    repo: str,
    commit_sha: str,
    committed_at: datetime,
    ref: str = "refs/heads/main",
) -> dict[str, Any]:
    """Build a minimal but schema-valid GitHub push webhook payload."""
    return {
        "ref": ref,
        "repository": {"full_name": repo},
        "commits": [
            {
                "id": commit_sha,
                "timestamp": _iso(committed_at),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Prometheus text format helpers
# ---------------------------------------------------------------------------


def parse_metric_value(
    prometheus_text: str,
    metric_name: str,
    labels: dict[str, str],
) -> float | None:
    """Extract a specific metric value from Prometheus text exposition output.

    Searches for a data line that:
      1. Starts with ``metric_name``
      2. Contains ALL provided label key="value" fragments

    Returns the float value if found, None otherwise.  Label key order in the
    output does not matter — each label is matched as an independent substring.
    """
    label_fragments = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    for line in prometheus_text.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if not line.startswith(metric_name):
            continue
        # Ensure all required labels appear in this line
        if not all(fragment in line for fragment in label_fragments):
            continue
        # The metric value is the last whitespace-delimited token on the line
        parts = line.rsplit(" ", 1)
        if len(parts) == 2:
            try:
                return float(parts[1])
            except ValueError:
                pass
    return None


def assert_metric_value(
    prometheus_text: str,
    metric_name: str,
    labels: dict[str, str],
    *,
    approx: float | None = None,
    exact: float | None = None,
    tolerance: float = 0.05,
) -> float:
    """Assert a DORA metric is present with the expected labels and value.

    Exactly one of ``approx`` or ``exact`` must be provided:

    - ``approx``: value must satisfy ``|actual - approx| <= tolerance``
    - ``exact``:  value must equal ``exact`` (float equality)

    Returns the actual observed value so callers can make additional assertions.
    """
    if approx is None and exact is None:
        raise ValueError("assert_metric_value: provide either approx= or exact=")

    value = parse_metric_value(prometheus_text, metric_name, labels)
    relevant_lines = [
        line
        for line in prometheus_text.splitlines()
        if line.startswith(metric_name)
    ]
    assert value is not None, (
        f"Metric {metric_name!r} with labels {labels!r} not found in /metrics output.\n"
        f"Relevant lines (name prefix match):\n"
        + ("\n".join(relevant_lines) if relevant_lines else "  <none>")
    )

    if exact is not None:
        assert value == exact, (
            f"{metric_name}{labels} expected exactly {exact}, got {value}"
        )
    elif approx is not None:
        assert abs(value - approx) <= tolerance, (
            f"{metric_name}{labels} expected ≈ {approx} (±{tolerance}), got {value}"
        )

    return value


def _metric_lines(prometheus_text: str, metric_name: str) -> list[str]:
    """Return data lines (non-comment) for the given metric name."""
    return [
        line.strip()
        for line in prometheus_text.splitlines()
        if line.strip().startswith(metric_name) and not line.strip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dora_store():
    """Fresh InMemoryEventStore per test — zero shared state across tests.

    Each test receives its own isolated store so event counts, timestamps,
    and state from one test cannot bleed into another.
    """
    from store import InMemoryEventStore

    return InMemoryEventStore()


@pytest.fixture()
def client(dora_store, monkeypatch):
    """FastAPI TestClient with an isolated store and WEBHOOK_SECRET configured.

    Injects ``dora_store`` via FastAPI's dependency_overrides mechanism so
    the webhook handler writes events into the per-test store, and the DORA
    calculators read from that same store when building the /metrics response.

    WEBHOOK_SECRET is set so that future HMAC verification can be enabled
    without changing these tests.
    """
    monkeypatch.setenv("WEBHOOK_SECRET", WEBHOOK_SECRET)

    import main
    from fastapi.testclient import TestClient

    # Override the DORA store dependency — the implementation must expose
    # get_dora_store as the FastAPI dependency that backs DORA calculators.
    main.app.dependency_overrides[main.get_dora_store] = lambda: dora_store

    with TestClient(main.app, raise_server_exceptions=True) as tc:
        yield tc

    # Teardown: restore default dependency so later tests are not affected
    main.app.dependency_overrides.pop(main.get_dora_store, None)


# ---------------------------------------------------------------------------
# Deployment Frequency
# ---------------------------------------------------------------------------


class TestDeploymentFrequencyMetric:
    """POST deployment_status(success) events → GET /metrics → frequency gauge.

    Deployment frequency measures how often an organisation deploys to production.
    GitWeave computes this as successful deployments per day over a 30-day window.
    """

    def test_10_successful_deployments_spread_over_30_days_yield_approx_0_33_per_day(
        self, client
    ):
        """10 deployments every 3 days over 30 days → frequency ≈ 0.33 per day.

        Arrange: POST 10 deployment_status(success) events spaced 3 days apart,
                 spanning a total window of 30 days relative to the current time.
        Act:     GET /metrics
        Assert:  gitweave_deployment_frequency_daily{repo=..., environment=...} ≈ 0.33
                 (= 10 deployments / 30-day window)
        """
        for i in range(10):
            # Events: day 0, day 3, day 6, …, day 27  (30-day span, 10 events)
            deploy_time = _NOW - timedelta(days=i * 3)
            payload = _make_deployment_status_payload(
                repo=REPO,
                state="success",
                environment=ENVIRONMENT,
                created_at=deploy_time,
                deployment_id=100 + i,
            )
            response = _post_webhook(client, "deployment_status", payload)
            assert response.status_code == 200, (
                f"deployment_status POST #{i} failed {response.status_code}: {response.text}"
            )

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_DEPLOYMENT_FREQUENCY,
            {"repo": REPO, "environment": ENVIRONMENT},
            approx=10 / 30,  # 0.333 per day
            tolerance=0.05,
        )

    def test_failed_deployments_are_excluded_from_frequency_count(self, client):
        """deployment_status(failure) events must not count toward deployment frequency.

        DORA deployment frequency tracks successful releases only.  Including
        failures would conflate cadence (how often we ship) with quality (how
        often we break things), obscuring both signals.
        """
        for i in range(5):
            deploy_time = _NOW - timedelta(days=i * 3)
            payload = _make_deployment_status_payload(
                repo=REPO,
                state="failure",
                environment=ENVIRONMENT,
                created_at=deploy_time,
                deployment_id=200 + i,
            )
            response = _post_webhook(client, "deployment_status", payload)
            assert response.status_code == 200

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_DEPLOYMENT_FREQUENCY,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=0.0,
        )

    def test_metric_carries_repo_and_environment_labels(self, client):
        """gitweave_deployment_frequency_daily must expose {repo=..., environment=...} labels.

        Label-based filtering lets operators query per-repo and per-environment
        deployment cadence independently in Prometheus and Grafana dashboards.
        """
        payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=999,
        )
        _post_webhook(client, "deployment_status", payload)

        metrics_response = client.get("/metrics")
        lines = _metric_lines(metrics_response.text, METRIC_DEPLOYMENT_FREQUENCY)

        assert lines, (
            f"No {METRIC_DEPLOYMENT_FREQUENCY!r} data lines found in /metrics output"
        )
        assert any(f'repo="{REPO}"' in line for line in lines), (
            f'Expected label repo="{REPO}" in metric output; lines: {lines}'
        )
        assert any(f'environment="{ENVIRONMENT}"' in line for line in lines), (
            f'Expected label environment="{ENVIRONMENT}" in metric output; lines: {lines}'
        )


# ---------------------------------------------------------------------------
# Lead Time for Changes
# ---------------------------------------------------------------------------


class TestLeadTimeForChangesMetric:
    """POST push + deployment_status events → GET /metrics → lead time gauge.

    Lead time measures the time from a code commit (push event) to that
    commit reaching production (deployment_status success).  GitWeave
    computes this as the average gap in hours between pushes and the
    subsequent successful deployment for the same repository.
    """

    def test_push_followed_by_successful_deployment_2h_later_yields_lead_time_of_2_hours(
        self, client
    ):
        """Push at T, deployment success at T+2h → lead time = 2.0 hours.

        Arrange: push event with commit timestamp T,
                 deployment_status(success) with created_at T+2h, same repo.
        Act:     GET /metrics
        Assert:  gitweave_lead_time_for_changes_hours{repo=..., environment=...} = 2.0
        """
        commit_sha = "abc123def456789"
        push_time = _NOW - timedelta(hours=2)
        deploy_time = _NOW  # 2 hours after the push

        push_payload = _make_push_payload(
            repo=REPO,
            commit_sha=commit_sha,
            committed_at=push_time,
        )
        deploy_payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=deploy_time,
            deployment_id=1,
        )

        response = _post_webhook(client, "push", push_payload)
        assert response.status_code == 200, (
            f"Push webhook failed {response.status_code}: {response.text}"
        )
        response = _post_webhook(client, "deployment_status", deploy_payload)
        assert response.status_code == 200, (
            f"Deployment webhook failed {response.status_code}: {response.text}"
        )

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_LEAD_TIME,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=2.0,
        )

    def test_failed_deployment_is_excluded_from_lead_time_calculation(self, client):
        """A push followed only by a failed deployment yields lead time = 0.0.

        Lead time represents the time to a successful production delivery.
        A failed deployment does not constitute a delivery; including it would
        make lead time appear artificially low on broken pipelines.
        """
        push_time = _NOW - timedelta(hours=5)
        push_payload = _make_push_payload(
            repo=REPO,
            commit_sha="deadbeef0000",
            committed_at=push_time,
        )
        deploy_payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=2,
        )

        _post_webhook(client, "push", push_payload)
        _post_webhook(client, "deployment_status", deploy_payload)

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_LEAD_TIME,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=0.0,
        )

    def test_metric_carries_repo_and_environment_labels(self, client):
        """gitweave_lead_time_for_changes_hours must expose {repo=..., environment=...} labels."""
        push_payload = _make_push_payload(
            repo=REPO,
            commit_sha="cafebabe1234",
            committed_at=_NOW - timedelta(hours=1),
        )
        deploy_payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=3,
        )
        _post_webhook(client, "push", push_payload)
        _post_webhook(client, "deployment_status", deploy_payload)

        metrics_response = client.get("/metrics")
        lines = _metric_lines(metrics_response.text, METRIC_LEAD_TIME)

        assert lines, (
            f"No {METRIC_LEAD_TIME!r} data lines found in /metrics output"
        )
        assert any(f'repo="{REPO}"' in line for line in lines), (
            f'Expected label repo="{REPO}" in metric output; lines: {lines}'
        )
        assert any(f'environment="{ENVIRONMENT}"' in line for line in lines), (
            f'Expected label environment="{ENVIRONMENT}" in metric output; lines: {lines}'
        )


# ---------------------------------------------------------------------------
# Change Failure Rate
# ---------------------------------------------------------------------------


class TestChangeFailureRateMetric:
    """POST deployment_status events → GET /metrics → CFR gauge.

    Change failure rate (CFR) is the fraction of deployments that result in
    a failure.  GitWeave computes this as:
        failures / (successes + failures)
    over the same 30-day rolling window used for deployment frequency.
    """

    def test_one_failure_and_one_success_yield_cfr_of_0_5(self, client):
        """1 failed + 1 successful deployment → CFR = 0.5.

        Arrange: POST deployment_status(failure) then deployment_status(success).
        Act:     GET /metrics
        Assert:  gitweave_change_failure_rate{repo=..., environment=...} = 0.5
        """
        failure_payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=_NOW - timedelta(hours=1),
            deployment_id=10,
        )
        success_payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=11,
        )

        response = _post_webhook(client, "deployment_status", failure_payload)
        assert response.status_code == 200, (
            f"Failure webhook failed {response.status_code}: {response.text}"
        )
        response = _post_webhook(client, "deployment_status", success_payload)
        assert response.status_code == 200, (
            f"Success webhook failed {response.status_code}: {response.text}"
        )

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_CFR,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=0.5,
        )

    def test_all_successful_deployments_yield_cfr_of_zero(self, client):
        """3 successful deployments, 0 failures → CFR = 0.0."""
        for i in range(3):
            payload = _make_deployment_status_payload(
                repo=REPO,
                state="success",
                environment=ENVIRONMENT,
                created_at=_NOW - timedelta(hours=i),
                deployment_id=20 + i,
            )
            response = _post_webhook(client, "deployment_status", payload)
            assert response.status_code == 200

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_CFR,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=0.0,
        )

    def test_all_failed_deployments_yield_cfr_of_one(self, client):
        """3 failed deployments, 0 successes → CFR = 1.0."""
        for i in range(3):
            payload = _make_deployment_status_payload(
                repo=REPO,
                state="failure",
                environment=ENVIRONMENT,
                created_at=_NOW - timedelta(hours=i),
                deployment_id=30 + i,
            )
            _post_webhook(client, "deployment_status", payload)

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_CFR,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=1.0,
        )

    def test_metric_carries_repo_and_environment_labels(self, client):
        """gitweave_change_failure_rate must expose {repo=..., environment=...} labels."""
        payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=40,
        )
        _post_webhook(client, "deployment_status", payload)

        metrics_response = client.get("/metrics")
        lines = _metric_lines(metrics_response.text, METRIC_CFR)

        assert lines, (
            f"No {METRIC_CFR!r} data lines found in /metrics output"
        )
        assert any(f'repo="{REPO}"' in line for line in lines), (
            f'Expected label repo="{REPO}" in metric output; lines: {lines}'
        )
        assert any(f'environment="{ENVIRONMENT}"' in line for line in lines), (
            f'Expected label environment="{ENVIRONMENT}" in metric output; lines: {lines}'
        )


# ---------------------------------------------------------------------------
# Mean Time to Restore
# ---------------------------------------------------------------------------


class TestMeanTimeToRestoreMetric:
    """POST failure + recovery deployment events → GET /metrics → MTTR gauge.

    Mean time to restore (MTTR) measures how quickly the team recovers from a
    production incident.  GitWeave computes this as the average time (in hours)
    between a deployment_status(failure) and the next deployment_status(success)
    for the same repository and environment.
    """

    def test_failure_at_t_then_recovery_3h_later_yields_mttr_of_3_hours(
        self, client
    ):
        """Deployment failure at T, recovery (success) at T+3h → MTTR = 3.0 hours.

        Arrange: deployment_status(failure) at T,
                 deployment_status(success) at T+3h, same repo and environment.
        Act:     GET /metrics
        Assert:  gitweave_mean_time_to_restore_hours{repo=..., environment=...} = 3.0
        """
        failure_time = _NOW - timedelta(hours=3)
        recovery_time = _NOW

        failure_payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=failure_time,
            deployment_id=50,
        )
        recovery_payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=recovery_time,
            deployment_id=51,
        )

        response = _post_webhook(client, "deployment_status", failure_payload)
        assert response.status_code == 200, (
            f"Failure webhook failed {response.status_code}: {response.text}"
        )
        response = _post_webhook(client, "deployment_status", recovery_payload)
        assert response.status_code == 200, (
            f"Recovery webhook failed {response.status_code}: {response.text}"
        )

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_MTTR,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=3.0,
        )

    def test_failure_with_no_subsequent_recovery_yields_mttr_of_zero(self, client):
        """An open incident with no recovery deployment → MTTR = 0.0.

        MTTR can only be computed for completed incident pairs (failure + recovery).
        An unresolved failure has no computable MTTR — emitting a misleading
        non-zero value would distort dashboards while the incident is active.
        """
        failure_payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=60,
        )
        response = _post_webhook(client, "deployment_status", failure_payload)
        assert response.status_code == 200

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        assert_metric_value(
            metrics_response.text,
            METRIC_MTTR,
            {"repo": REPO, "environment": ENVIRONMENT},
            exact=0.0,
        )

    def test_metric_carries_repo_and_environment_labels(self, client):
        """gitweave_mean_time_to_restore_hours must expose {repo=..., environment=...} labels."""
        failure_payload = _make_deployment_status_payload(
            repo=REPO,
            state="failure",
            environment=ENVIRONMENT,
            created_at=_NOW - timedelta(hours=1),
            deployment_id=70,
        )
        recovery_payload = _make_deployment_status_payload(
            repo=REPO,
            state="success",
            environment=ENVIRONMENT,
            created_at=_NOW,
            deployment_id=71,
        )
        _post_webhook(client, "deployment_status", failure_payload)
        _post_webhook(client, "deployment_status", recovery_payload)

        metrics_response = client.get("/metrics")
        lines = _metric_lines(metrics_response.text, METRIC_MTTR)

        assert lines, (
            f"No {METRIC_MTTR!r} data lines found in /metrics output"
        )
        assert any(f'repo="{REPO}"' in line for line in lines), (
            f'Expected label repo="{REPO}" in metric output; lines: {lines}'
        )
        assert any(f'environment="{ENVIRONMENT}"' in line for line in lines), (
            f'Expected label environment="{ENVIRONMENT}" in metric output; lines: {lines}'
        )


# ---------------------------------------------------------------------------
# Cross-test isolation
# ---------------------------------------------------------------------------


class TestEventStoreIsolation:
    """Verify that tests receive independent stores with no shared state."""

    def test_event_store_is_empty_at_start_of_each_test(self, dora_store):
        """The dora_store fixture must provide a zero-event store to every test.

        If store state leaked across tests, the first test's events would
        inflate metrics in subsequent tests, producing false passes or cascading
        failures that are hard to diagnose.
        """
        events = dora_store.get_events(
            repo=REPO,
            event_type="deployment_status",
            since_dt=_NOW - timedelta(days=365),
        )
        assert events == [], (
            f"dora_store must be empty at test start; found {len(events)} events"
        )

    def test_two_successive_deployments_accumulate_within_same_test(self, client, dora_store):
        """Within a single test, multiple POST /webhook calls accumulate in the store."""
        initial_count = len(
            dora_store.get_events(
                repo=REPO,
                event_type="deployment_status",
                since_dt=_NOW - timedelta(days=1),
            )
        )

        for deploy_id in (80, 81):
            _post_webhook(
                client,
                "deployment_status",
                _make_deployment_status_payload(
                    repo=REPO,
                    state="success",
                    environment=ENVIRONMENT,
                    created_at=_NOW - timedelta(minutes=deploy_id),
                    deployment_id=deploy_id,
                ),
            )

        final_count = len(
            dora_store.get_events(
                repo=REPO,
                event_type="deployment_status",
                since_dt=_NOW - timedelta(days=1),
            )
        )
        assert final_count == initial_count + 2, (
            f"Expected store to grow by 2 after two POSTs; "
            f"grew by {final_count - initial_count}"
        )
