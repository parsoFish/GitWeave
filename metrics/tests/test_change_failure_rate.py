"""TDD tests for the DORA Change Failure Rate metric.

Change Failure Rate: the proportion of deployments in the last 30 days that
resulted in a production failure.

Exposed as: gitweave_change_failure_rate Prometheus Gauge (0.0–1.0)
Labels: repository, environment

Formula:
  numerator   = count(state='failure' OR state='error' in last 30 days)
  denominator = count(state='success' OR state='failure' OR state='error' in last 30 days)
  CFR         = numerator / denominator   (0.0 when denominator == 0)

States 'pending' and 'in_progress' are excluded from BOTH numerator and
denominator.  A deployment exactly 30 days ago is within the window; one
30 days + 1 second ago is outside it.

Metric updates synchronously after each deployment_status event is stored.

These tests are written BEFORE implementation (TDD red phase) and will FAIL
until metrics/src/dora/change_failure_rate.py is created and
metrics/src/handlers/deployment_status.py is updated to update the gauge.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

# Add src to path so we can import handler modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _days_ago(n: float, relative_to: datetime | None = None) -> datetime:
    """Return a timezone-aware datetime n days before `relative_to` (default: now)."""
    base = relative_to or _utcnow()
    return base - timedelta(days=n)


def _make_store():
    """Return a fresh InMemoryEventStore."""
    from store import InMemoryEventStore

    return InMemoryEventStore()


def _make_deployment_event(
    *,
    repo: str = "octocat/Hello-World",
    environment: str = "production",
    state: str = "success",
    created_at: datetime | None = None,
    deployment_id: int = 1,
) -> dict[str, Any]:
    """Build a normalised deployment_status event dict as produced by the handler."""
    return {
        "event_type": "deployment_status",
        "repo": repo,
        "environment": environment,
        "state": state,
        "created_at": created_at or _utcnow(),
        "deployment_id": deployment_id,
    }


def _make_handle_payload(
    *,
    repo: str = "octocat/Hello-World",
    environment: str = "production",
    state: str = "success",
    deployment_id: int = 1,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a raw GitHub deployment_status webhook payload."""
    ts = (created_at or _utcnow()).isoformat()
    return {
        "deployment_status": {
            "state": state,
            "id": deployment_id,
            "created_at": ts,
            "environment": environment,
        },
        "repository": {"full_name": repo},
    }


# ---------------------------------------------------------------------------
# Unit tests — calculate_change_failure_rate() pure function
# ---------------------------------------------------------------------------


class TestCalculateChangeFailureRate:
    """calculate_change_failure_rate(repo, environment, store, now) returns a float."""

    def test_zero_deployments_returns_0_0_no_division_by_zero(self):
        """Empty store must return 0.0 — not raise ZeroDivisionError."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_all_success_deployments_returns_0_0(self):
        """When all deployments are 'success' the failure rate is 0.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        for i in range(10):
            store.store_event(
                _make_deployment_event(state="success", deployment_id=i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_all_failure_deployments_returns_1_0(self):
        """When all counted deployments are 'failure' the rate is 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        for i in range(5):
            store.store_event(
                _make_deployment_event(state="failure", deployment_id=i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1.0)

    def test_all_error_deployments_returns_1_0(self):
        """When all counted deployments are 'error' the rate is 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        for i in range(3):
            store.store_event(
                _make_deployment_event(state="error", deployment_id=i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1.0)

    def test_one_failure_one_success_returns_0_5(self):
        """1 failure + 1 success → CFR = 0.5."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=_days_ago(1, now)))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=_days_ago(2, now)))

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.5)

    def test_one_error_one_success_returns_0_5(self):
        """1 error + 1 success → CFR = 0.5 (error counts as failure)."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        store.store_event(_make_deployment_event(state="error", deployment_id=1, created_at=_days_ago(1, now)))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=_days_ago(2, now)))

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.5)

    def test_in_progress_excluded_from_numerator_and_denominator(self):
        """'in_progress' deployments must not affect numerator or denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # 1 success, 1 failure, 5 in_progress — CFR should be 0.5, not 1/7
        store.store_event(_make_deployment_event(state="success", deployment_id=1, created_at=_days_ago(1, now)))
        store.store_event(_make_deployment_event(state="failure", deployment_id=2, created_at=_days_ago(2, now)))
        for i in range(5):
            store.store_event(
                _make_deployment_event(state="in_progress", deployment_id=10 + i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.5)

    def test_pending_excluded_from_numerator_and_denominator(self):
        """'pending' deployments must not affect numerator or denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # 2 success, 1 failure, 3 pending — CFR should be 1/3, not 1/6
        store.store_event(_make_deployment_event(state="success", deployment_id=1, created_at=_days_ago(1, now)))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=_days_ago(2, now)))
        store.store_event(_make_deployment_event(state="failure", deployment_id=3, created_at=_days_ago(3, now)))
        for i in range(3):
            store.store_event(
                _make_deployment_event(state="pending", deployment_id=20 + i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1 / 3)

    def test_both_pending_and_in_progress_excluded_together(self):
        """Both 'pending' and 'in_progress' are excluded; only success/failure/error count."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # 3 success, 1 error, 4 pending, 4 in_progress → CFR = 1/4
        for i in range(3):
            store.store_event(
                _make_deployment_event(state="success", deployment_id=i, created_at=_days_ago(i, now))
            )
        store.store_event(_make_deployment_event(state="error", deployment_id=30, created_at=_days_ago(1, now)))
        for i in range(4):
            store.store_event(
                _make_deployment_event(state="pending", deployment_id=40 + i, created_at=_days_ago(i, now))
            )
        for i in range(4):
            store.store_event(
                _make_deployment_event(state="in_progress", deployment_id=50 + i, created_at=_days_ago(i, now))
            )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1 / 4)

    def test_deployment_exactly_30_days_ago_is_included(self):
        """A deployment at exactly 30 days ago falls within the 30-day window."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()
        boundary = _days_ago(30, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=boundary))

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1.0)

    def test_deployment_just_over_30_days_ago_is_excluded(self):
        """A deployment at 30 days + 1 second ago falls outside the 30-day window."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()
        just_outside = _days_ago(30, relative_to=now) - timedelta(seconds=1)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=just_outside))

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_deployments_for_different_repo_are_not_counted(self):
        """Deployments from another repo do not affect the target repo's CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # 5 failures for other/repo — should not bleed into octocat/Hello-World
        for i in range(5):
            store.store_event(
                _make_deployment_event(
                    repo="other/repo", state="failure", deployment_id=i, created_at=_days_ago(i, now)
                )
            )
        store.store_event(
            _make_deployment_event(
                repo="octocat/Hello-World", state="success", deployment_id=100, created_at=_days_ago(1, now)
            )
        )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_deployments_for_different_environment_are_not_counted(self):
        """Deployments to another environment do not affect the target environment's CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # 5 failures in staging — should not bleed into production
        for i in range(5):
            store.store_event(
                _make_deployment_event(
                    environment="staging", state="failure", deployment_id=i, created_at=_days_ago(i, now)
                )
            )
        store.store_event(
            _make_deployment_event(
                environment="production", state="success", deployment_id=100, created_at=_days_ago(1, now)
            )
        )

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_multiple_repos_and_environments_are_isolated(self):
        """CFR for different repo+environment combinations are independent."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()

        # repo-a/production: 2 success, 2 failure → CFR = 0.5
        for i in range(2):
            store.store_event(
                _make_deployment_event(
                    repo="org/repo-a", environment="production",
                    state="success", deployment_id=i, created_at=_days_ago(i + 1, now),
                )
            )
        for i in range(2):
            store.store_event(
                _make_deployment_event(
                    repo="org/repo-a", environment="production",
                    state="failure", deployment_id=10 + i, created_at=_days_ago(i + 1, now),
                )
            )

        # repo-b/staging: 9 success, 1 error → CFR = 0.1
        for i in range(9):
            store.store_event(
                _make_deployment_event(
                    repo="org/repo-b", environment="staging",
                    state="success", deployment_id=100 + i, created_at=_days_ago(i + 1, now),
                )
            )
        store.store_event(
            _make_deployment_event(
                repo="org/repo-b", environment="staging",
                state="error", deployment_id=200, created_at=_days_ago(1, now),
            )
        )

        cfr_a = calculate_change_failure_rate("org/repo-a", "production", store, now)
        cfr_b = calculate_change_failure_rate("org/repo-b", "staging", store, now)

        assert cfr_a == pytest.approx(0.5)
        assert cfr_b == pytest.approx(0.1)

    @pytest.mark.parametrize(
        "n_success,n_failure,n_error,n_pending,n_in_progress,expected_cfr",
        [
            # (successes, failures, errors, pending, in_progress, expected)
            (0, 0, 0, 0, 0, 0.0),    # empty → 0.0, no ZeroDivisionError
            (10, 0, 0, 0, 0, 0.0),   # all success → 0.0
            (0, 10, 0, 0, 0, 1.0),   # all failure → 1.0
            (0, 0, 10, 0, 0, 1.0),   # all error → 1.0
            (1, 1, 0, 0, 0, 0.5),    # 1 success + 1 failure → 0.5
            (1, 0, 1, 0, 0, 0.5),    # 1 success + 1 error → 0.5
            (3, 1, 0, 5, 5, 0.25),   # pending + in_progress excluded → 1/4
            (0, 1, 0, 10, 10, 1.0),  # excluded states don't bleed into denominator
            (2, 1, 1, 3, 3, 0.5),    # 2 success + 1 failure + 1 error = 4 total, 2 fail → 0.5
        ],
    )
    def test_parametrized_state_combinations(
        self,
        n_success: int,
        n_failure: int,
        n_error: int,
        n_pending: int,
        n_in_progress: int,
        expected_cfr: float,
    ):
        """Parametrized verification of CFR formula across all state combinations."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _make_store()
        now = _utcnow()
        deployment_id = 0

        for state, count in [
            ("success", n_success),
            ("failure", n_failure),
            ("error", n_error),
            ("pending", n_pending),
            ("in_progress", n_in_progress),
        ]:
            for _ in range(count):
                store.store_event(
                    _make_deployment_event(
                        state=state,
                        deployment_id=deployment_id,
                        created_at=_days_ago(1, now),
                    )
                )
                deployment_id += 1

        result = calculate_change_failure_rate("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(expected_cfr)


# ---------------------------------------------------------------------------
# Prometheus gauge registration tests
# ---------------------------------------------------------------------------


class TestChangeFailureRateGaugeRegistration:
    """gitweave_change_failure_rate Prometheus gauge must be registered correctly."""

    def test_change_failure_rate_gauge_is_importable(self):
        """CHANGE_FAILURE_RATE_GAUGE must be importable from the module."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert CHANGE_FAILURE_RATE_GAUGE is not None

    def test_gauge_name_is_gitweave_change_failure_rate(self):
        """The Prometheus metric name must be 'gitweave_change_failure_rate'."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert CHANGE_FAILURE_RATE_GAUGE._name == "gitweave_change_failure_rate"

    def test_gauge_has_repository_label(self):
        """The gauge must carry a 'repository' label for per-repo cardinality."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert "repository" in CHANGE_FAILURE_RATE_GAUGE._labelnames

    def test_gauge_has_environment_label(self):
        """The gauge must carry an 'environment' label for per-environment cardinality."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert "environment" in CHANGE_FAILURE_RATE_GAUGE._labelnames

    def test_gauge_has_exactly_two_labels(self):
        """The gauge must have exactly two labels: repository and environment."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert set(CHANGE_FAILURE_RATE_GAUGE._labelnames) == {"repository", "environment"}


# ---------------------------------------------------------------------------
# Integration tests — gauge updates synchronously after handle()
# ---------------------------------------------------------------------------


class TestChangeFailureRateGaugeUpdatesAfterHandle:
    """The Prometheus gauge must reflect the current CFR after each handle() call."""

    def _read_gauge(self, repo: str, environment: str) -> float:
        """Read the current value of the gauge for a given repo+environment."""
        from prometheus_client import REGISTRY

        for metric in REGISTRY.collect():
            if metric.name == "gitweave_change_failure_rate":
                for sample in metric.samples:
                    if (
                        sample.labels.get("repository") == repo
                        and sample.labels.get("environment") == environment
                    ):
                        return sample.value
        return 0.0

    def test_gauge_updated_to_1_0_after_single_failure(self):
        """A single failure with no successes sets the gauge to 1.0."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/single-failure",
                environment="production",
                state="failure",
                deployment_id=1,
            ),
            store,
        )

        value = self._read_gauge("cfr-gauge-test/single-failure", "production")
        assert value == pytest.approx(1.0)

    def test_gauge_updated_to_0_0_after_single_success(self):
        """A single success with no failures leaves the gauge at 0.0."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/single-success",
                environment="production",
                state="success",
                deployment_id=1,
            ),
            store,
        )

        value = self._read_gauge("cfr-gauge-test/single-success", "production")
        assert value == pytest.approx(0.0)

    def test_gauge_updated_to_0_5_after_equal_success_and_failure(self):
        """Gauge equals 0.5 when success and failure counts are equal."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = datetime.now(tz=timezone.utc)

        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/equal-mix",
                environment="production",
                state="success",
                deployment_id=1,
                created_at=_days_ago(1, now),
            ),
            store,
        )
        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/equal-mix",
                environment="production",
                state="failure",
                deployment_id=2,
                created_at=_days_ago(2, now),
            ),
            store,
        )

        value = self._read_gauge("cfr-gauge-test/equal-mix", "production")
        assert value == pytest.approx(0.5)

    def test_gauge_not_updated_by_in_progress_event(self):
        """An 'in_progress' event alone must not set the gauge (remains at 0.0 for new repo)."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/in-progress-only",
                environment="staging",
                state="in_progress",
                deployment_id=1,
            ),
            store,
        )

        # Gauge should reflect 0/0 → 0.0 (no counted deployments)
        value = self._read_gauge("cfr-gauge-test/in-progress-only", "staging")
        assert value == pytest.approx(0.0)

    def test_gauge_not_updated_by_pending_event(self):
        """A 'pending' event alone must not set the gauge (remains at 0.0 for new repo)."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        handle(
            _make_handle_payload(
                repo="cfr-gauge-test/pending-only",
                environment="staging",
                state="pending",
                deployment_id=1,
            ),
            store,
        )

        value = self._read_gauge("cfr-gauge-test/pending-only", "staging")
        assert value == pytest.approx(0.0)

    def test_gauge_updates_independently_per_repo_and_environment(self):
        """Gauge is independent across different repo+environment combinations."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = datetime.now(tz=timezone.utc)

        # repo-x/production: 3 success, 1 failure → CFR = 0.25
        for i in range(3):
            handle(
                _make_handle_payload(
                    repo="cfr-isolation-test/repo-x",
                    environment="production",
                    state="success",
                    deployment_id=i,
                    created_at=_days_ago(i + 1, now),
                ),
                store,
            )
        handle(
            _make_handle_payload(
                repo="cfr-isolation-test/repo-x",
                environment="production",
                state="failure",
                deployment_id=99,
                created_at=_days_ago(1, now),
            ),
            store,
        )

        # repo-y/staging: all error → CFR = 1.0
        for i in range(4):
            handle(
                _make_handle_payload(
                    repo="cfr-isolation-test/repo-y",
                    environment="staging",
                    state="error",
                    deployment_id=200 + i,
                    created_at=_days_ago(i + 1, now),
                ),
                store,
            )

        cfr_x = self._read_gauge("cfr-isolation-test/repo-x", "production")
        cfr_y = self._read_gauge("cfr-isolation-test/repo-y", "staging")

        assert cfr_x == pytest.approx(0.25)
        assert cfr_y == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Module structure tests — ensure dora.change_failure_rate can be imported
# ---------------------------------------------------------------------------


class TestChangeFailureRateModuleStructure:
    """The dora.change_failure_rate module must be discoverable and well-formed."""

    def test_dora_change_failure_rate_module_is_importable(self):
        """import dora.change_failure_rate must succeed."""
        import dora.change_failure_rate  # noqa: F401

    def test_calculate_change_failure_rate_is_callable(self):
        """calculate_change_failure_rate must be a callable exported from the module."""
        from dora.change_failure_rate import calculate_change_failure_rate

        assert callable(calculate_change_failure_rate)

    def test_change_failure_rate_gauge_constant_exists(self):
        """CHANGE_FAILURE_RATE_GAUGE must be exported from the module."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert CHANGE_FAILURE_RATE_GAUGE is not None

    def test_function_signature_accepts_repo_environment_store_now(self):
        """calculate_change_failure_rate must accept (repo, environment, store, now)."""
        import inspect
        from dora.change_failure_rate import calculate_change_failure_rate

        sig = inspect.signature(calculate_change_failure_rate)
        param_names = list(sig.parameters.keys())

        assert param_names == ["repo", "environment", "store", "now"]
