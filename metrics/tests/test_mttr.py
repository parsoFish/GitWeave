"""TDD tests for the DORA Mean Time to Restore (MTTR) metric.

Mean Time to Restore: the median duration between a production failure and the
subsequent successful recovery deployment.

Exposed as: gitweave_mttr_hours Prometheus Gauge
Labels: repository, environment

Formula:
  For each repo+environment combination:
    1. Collect all deployment_status events in the last 30 days.
    2. Walk events in chronological order.
    3. Identify failure→recovery pairs:
       - Failure: state='failure' OR state='error'
       - Recovery: the next state='success' after a failure
       - Consecutive failures before a recovery: only the LAST failure counts
    4. duration = recovery.created_at - (last failure before recovery).created_at
    5. MTTR = median(all durations in hours)
  Unpaired failures (no subsequent success in window) are excluded.
  Returns 0.0 when no failure→recovery pairs exist.

These tests are written BEFORE implementation (TDD red phase) and will FAIL
until metrics/src/dora/mttr.py is created and
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


def _dt(days_ago: float = 0, hours_ago: float = 0, relative_to: datetime | None = None) -> datetime:
    """Return a timezone-aware datetime offset before `relative_to` (default: now)."""
    base = relative_to or _utcnow()
    return base - timedelta(days=days_ago, hours=hours_ago)


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
    """Build a normalised deployment_status event dict as stored by the handler."""
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
# Unit tests — calculate_mttr() pure function
# ---------------------------------------------------------------------------


class TestCalculateMttr:
    """calculate_mttr(repo, environment, store, now) returns a float (hours)."""

    def test_empty_store_returns_0_0(self):
        """Empty store must return 0.0 — no pairs, no ZeroDivisionError."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_only_success_deployments_returns_0_0(self):
        """When there are only success deployments (no failures), MTTR is 0.0."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        for i in range(5):
            store.store_event(
                _make_deployment_event(state="success", deployment_id=i, created_at=_dt(days_ago=i, relative_to=now))
            )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_single_failure_with_no_recovery_returns_0_0(self):
        """An unpaired failure (no subsequent success) is excluded — returns 0.0."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        store.store_event(
            _make_deployment_event(state="failure", deployment_id=1, created_at=_dt(days_ago=1, relative_to=now))
        )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_single_error_with_no_recovery_returns_0_0(self):
        """An unpaired error (state='error', no subsequent success) is excluded — returns 0.0."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        store.store_event(
            _make_deployment_event(state="error", deployment_id=1, created_at=_dt(days_ago=1, relative_to=now))
        )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_single_failure_followed_by_recovery_returns_correct_hours(self):
        """A single failure→success pair returns the duration in hours."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # failure 4 hours ago, recovery 2 hours ago → 2 hours restore time
        failure_time = _dt(hours_ago=4, relative_to=now)
        recovery_time = _dt(hours_ago=2, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=failure_time))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=recovery_time))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(2.0, abs=1e-6)

    def test_single_error_followed_by_recovery_returns_correct_hours(self):
        """An error (state='error')→success pair counts as a failure→recovery."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # error 4 hours ago, recovery 2 hours ago → 2 hours restore time
        failure_time = _dt(hours_ago=4, relative_to=now)
        recovery_time = _dt(hours_ago=2, relative_to=now)

        store.store_event(_make_deployment_event(state="error", deployment_id=1, created_at=failure_time))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=recovery_time))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(2.0, abs=1e-6)

    def test_multiple_pairs_returns_median(self):
        """Multiple failure→recovery pairs: MTTR is the median of durations (not mean)."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # Three pairs with durations: 2h, 4h, 6h → median = 4h
        # pair 1: failure at base1-2h, recovery at base1 → 2h
        # pair 2: failure at base2-4h, recovery at base2 → 4h
        # pair 3: failure at base3-6h, recovery at base3 → 6h
        base1 = _dt(days_ago=10, relative_to=now)
        base2 = _dt(days_ago=7, relative_to=now)
        base3 = _dt(days_ago=4, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=base1 - timedelta(hours=2)))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=base1))
        store.store_event(_make_deployment_event(state="failure", deployment_id=3, created_at=base2 - timedelta(hours=4)))
        store.store_event(_make_deployment_event(state="success", deployment_id=4, created_at=base2))
        store.store_event(_make_deployment_event(state="failure", deployment_id=5, created_at=base3 - timedelta(hours=6)))
        store.store_event(_make_deployment_event(state="success", deployment_id=6, created_at=base3))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(4.0, abs=1e-6)

    def test_even_number_of_pairs_returns_median(self):
        """With an even number of pairs, median is the average of the two middle values."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # Four pairs with durations: 1h, 3h, 5h, 7h → median = (3+5)/2 = 4h
        durations = (1, 3, 5, 7)
        for i, duration in enumerate(durations):
            base = _dt(days_ago=20 - i * 4, relative_to=now)
            store.store_event(
                _make_deployment_event(
                    state="failure",
                    deployment_id=10 + i,
                    created_at=base - timedelta(hours=duration),
                )
            )
            store.store_event(
                _make_deployment_event(state="success", deployment_id=10 + i + 1, created_at=base)
            )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(4.0, abs=1e-6)

    def test_consecutive_failures_before_recovery_only_last_counts(self):
        """When multiple failures occur before a recovery, only the LAST failure starts the timer."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # first failure at -10h, last failure at -2h, recovery at now
        # only last failure counts → 2h restore time
        first_failure = _dt(hours_ago=10, relative_to=now)
        last_failure = _dt(hours_ago=2, relative_to=now)
        recovery = _dt(hours_ago=0, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=first_failure))
        store.store_event(_make_deployment_event(state="failure", deployment_id=2, created_at=last_failure))
        store.store_event(_make_deployment_event(state="success", deployment_id=3, created_at=recovery))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(2.0, abs=0.01)

    def test_consecutive_errors_before_recovery_only_last_counts(self):
        """Consecutive 'error' states: only the last error before a recovery counts."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # errors at -8h, -4h, -1h; recovery at now → only last error counts → 1h
        error1 = _dt(hours_ago=8, relative_to=now)
        error2 = _dt(hours_ago=4, relative_to=now)
        error3 = _dt(hours_ago=1, relative_to=now)
        recovery = _dt(hours_ago=0, relative_to=now)

        store.store_event(_make_deployment_event(state="error", deployment_id=1, created_at=error1))
        store.store_event(_make_deployment_event(state="error", deployment_id=2, created_at=error2))
        store.store_event(_make_deployment_event(state="error", deployment_id=3, created_at=error3))
        store.store_event(_make_deployment_event(state="success", deployment_id=4, created_at=recovery))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(1.0, abs=0.01)

    def test_mixed_consecutive_failure_and_error_before_recovery_only_last_counts(self):
        """Mixed consecutive failures/errors: only the chronologically last one before recovery counts."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # failure at -5h, error at -3h, success at now → last failure-like is error at -3h → 3h
        failure = _dt(hours_ago=5, relative_to=now)
        error = _dt(hours_ago=3, relative_to=now)
        recovery = _dt(hours_ago=0, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=failure))
        store.store_event(_make_deployment_event(state="error", deployment_id=2, created_at=error))
        store.store_event(_make_deployment_event(state="success", deployment_id=3, created_at=recovery))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(3.0, abs=0.01)

    def test_unpaired_failure_after_paired_failures_excluded(self):
        """A trailing unpaired failure (no subsequent success in window) is excluded from MTTR."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # paired failure at -10h → recovery at -8h (2h duration)
        # then unpaired failure at -3h → no recovery → excluded
        paired_failure = _dt(hours_ago=10, relative_to=now)
        paired_recovery = _dt(hours_ago=8, relative_to=now)
        unpaired_failure = _dt(hours_ago=3, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=paired_failure))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=paired_recovery))
        store.store_event(_make_deployment_event(state="failure", deployment_id=3, created_at=unpaired_failure))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        # only the 2h pair counts; unpaired is excluded
        assert result == pytest.approx(2.0, abs=1e-6)

    def test_failure_outside_30_day_window_excluded(self):
        """A failure older than 30 days is outside the window and must not create a pair."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # failure just outside window (30 days + 1 second ago)
        old_failure = _dt(days_ago=30, relative_to=now) - timedelta(seconds=1)
        recovery = _dt(days_ago=1, relative_to=now)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=old_failure))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=recovery))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_failure_at_exactly_30_days_ago_is_included(self):
        """A failure at exactly 30 days ago is within the window and may form a pair."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # failure exactly 30 days ago, recovery 6 hours later
        boundary_failure = now - timedelta(days=30)
        recovery = boundary_failure + timedelta(hours=6)

        store.store_event(_make_deployment_event(state="failure", deployment_id=1, created_at=boundary_failure))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=recovery))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(6.0, abs=1e-6)

    def test_deployments_for_different_repo_not_counted(self):
        """Deployments from another repo do not affect the target repo's MTTR."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # other/repo: failure→success pair (should not affect octocat/Hello-World)
        store.store_event(
            _make_deployment_event(repo="other/repo", state="failure", deployment_id=1, created_at=_dt(days_ago=2, relative_to=now))
        )
        store.store_event(
            _make_deployment_event(repo="other/repo", state="success", deployment_id=2, created_at=_dt(days_ago=1, relative_to=now))
        )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_deployments_for_different_environment_not_counted(self):
        """Deployments to another environment do not affect the target environment's MTTR."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # staging: failure→success pair (should not affect production)
        store.store_event(
            _make_deployment_event(environment="staging", state="failure", deployment_id=1, created_at=_dt(days_ago=2, relative_to=now))
        )
        store.store_event(
            _make_deployment_event(environment="staging", state="success", deployment_id=2, created_at=_dt(days_ago=1, relative_to=now))
        )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    def test_multiple_repos_and_environments_isolated(self):
        """MTTR calculations for different repo+environment combinations are independent."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # org/repo-a/production: failure at -6h, recovery at -2h → 4h
        base_a = _dt(days_ago=5, relative_to=now)
        store.store_event(
            _make_deployment_event(
                repo="org/repo-a", environment="production",
                state="failure", deployment_id=1,
                created_at=base_a - timedelta(hours=4),
            )
        )
        store.store_event(
            _make_deployment_event(
                repo="org/repo-a", environment="production",
                state="success", deployment_id=2,
                created_at=base_a,
            )
        )

        # org/repo-b/staging: error at -10h, recovery at -2h → 8h
        base_b = _dt(days_ago=3, relative_to=now)
        store.store_event(
            _make_deployment_event(
                repo="org/repo-b", environment="staging",
                state="error", deployment_id=3,
                created_at=base_b - timedelta(hours=8),
            )
        )
        store.store_event(
            _make_deployment_event(
                repo="org/repo-b", environment="staging",
                state="success", deployment_id=4,
                created_at=base_b,
            )
        )

        mttr_a = calculate_mttr("org/repo-a", "production", store, now)
        mttr_b = calculate_mttr("org/repo-b", "staging", store, now)

        assert mttr_a == pytest.approx(4.0, abs=1e-6)
        assert mttr_b == pytest.approx(8.0, abs=1e-6)

    def test_success_before_failure_does_not_form_pair(self):
        """A success that precedes a failure does not retroactively pair as a recovery."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        # success first, then failure — no pair exists
        store.store_event(
            _make_deployment_event(state="success", deployment_id=1, created_at=_dt(hours_ago=10, relative_to=now))
        )
        store.store_event(
            _make_deployment_event(state="failure", deployment_id=2, created_at=_dt(hours_ago=1, relative_to=now))
        )

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "failure_state,restore_hours,expected_mttr",
        [
            ("failure", 1.0, 1.0),
            ("error", 2.5, 2.5),
            ("failure", 24.0, 24.0),
            ("error", 0.5, 0.5),
        ],
    )
    def test_parametrized_single_pair_duration(
        self,
        failure_state: str,
        restore_hours: float,
        expected_mttr: float,
    ):
        """Single pair with various failure states and durations returns correct MTTR."""
        from dora.mttr import calculate_mttr

        store = _make_store()
        now = _utcnow()

        failure_time = _dt(hours_ago=restore_hours, relative_to=now) - timedelta(hours=1)
        recovery_time = failure_time + timedelta(hours=restore_hours)

        store.store_event(_make_deployment_event(state=failure_state, deployment_id=1, created_at=failure_time))
        store.store_event(_make_deployment_event(state="success", deployment_id=2, created_at=recovery_time))

        result = calculate_mttr("octocat/Hello-World", "production", store, now)

        assert result == pytest.approx(expected_mttr, abs=0.0001)


# ---------------------------------------------------------------------------
# Prometheus gauge registration tests
# ---------------------------------------------------------------------------


class TestMttrGaugeRegistration:
    """gitweave_mttr_hours Prometheus gauge must be registered correctly."""

    def test_mttr_gauge_is_importable(self):
        """MTTR_GAUGE must be importable from the module."""
        from dora.mttr import MTTR_GAUGE

        assert MTTR_GAUGE is not None

    def test_gauge_name_is_gitweave_mttr_hours(self):
        """The Prometheus metric name must be 'gitweave_mttr_hours'."""
        from dora.mttr import MTTR_GAUGE

        assert MTTR_GAUGE._name == "gitweave_mttr_hours"

    def test_gauge_has_repository_label(self):
        """The gauge must carry a 'repository' label for per-repo cardinality."""
        from dora.mttr import MTTR_GAUGE

        assert "repository" in MTTR_GAUGE._labelnames

    def test_gauge_has_environment_label(self):
        """The gauge must carry an 'environment' label for per-environment cardinality."""
        from dora.mttr import MTTR_GAUGE

        assert "environment" in MTTR_GAUGE._labelnames

    def test_gauge_has_exactly_two_labels(self):
        """The gauge must have exactly two labels: repository and environment."""
        from dora.mttr import MTTR_GAUGE

        assert set(MTTR_GAUGE._labelnames) == {"repository", "environment"}


# ---------------------------------------------------------------------------
# Integration tests — gauge updates synchronously after handle()
# ---------------------------------------------------------------------------


class TestMttrGaugeUpdatesAfterHandle:
    """The Prometheus gauge must reflect the current MTTR after each handle() call."""

    def _read_gauge(self, repo: str, environment: str) -> float:
        """Read the current value of the gitweave_mttr_hours gauge for a given repo+environment."""
        from prometheus_client import REGISTRY

        for metric in REGISTRY.collect():
            if metric.name == "gitweave_mttr_hours":
                for sample in metric.samples:
                    if (
                        sample.labels.get("repository") == repo
                        and sample.labels.get("environment") == environment
                    ):
                        return sample.value
        return 0.0

    def test_gauge_stays_0_0_after_single_failure_only(self):
        """An unpaired failure must not set the gauge above 0.0."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        handle(
            _make_handle_payload(
                repo="mttr-gauge-test/unpaired-failure",
                environment="production",
                state="failure",
                deployment_id=1,
            ),
            store,
        )

        value = self._read_gauge("mttr-gauge-test/unpaired-failure", "production")
        assert value == pytest.approx(0.0)

    def test_gauge_updated_after_failure_then_recovery(self):
        """Gauge reflects the restore time (hours) after a failure→success pair is stored."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = datetime.now(tz=timezone.utc)

        # failure 3 hours ago, recovery now → 3h MTTR
        failure_time = now - timedelta(hours=3)
        recovery_time = now

        handle(
            _make_handle_payload(
                repo="mttr-gauge-test/one-pair",
                environment="production",
                state="failure",
                deployment_id=1,
                created_at=failure_time,
            ),
            store,
        )
        handle(
            _make_handle_payload(
                repo="mttr-gauge-test/one-pair",
                environment="production",
                state="success",
                deployment_id=2,
                created_at=recovery_time,
            ),
            store,
        )

        value = self._read_gauge("mttr-gauge-test/one-pair", "production")
        assert value == pytest.approx(3.0, abs=0.1)

    def test_gauge_updated_independently_per_repo_and_environment(self):
        """Gauge is independent across different repo+environment combinations."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = datetime.now(tz=timezone.utc)

        # repo-x/production: failure 2h ago → success now → 2h MTTR
        failure_x = now - timedelta(hours=2)
        handle(
            _make_handle_payload(
                repo="mttr-isolation-test/repo-x",
                environment="production",
                state="failure",
                deployment_id=1,
                created_at=failure_x,
            ),
            store,
        )
        handle(
            _make_handle_payload(
                repo="mttr-isolation-test/repo-x",
                environment="production",
                state="success",
                deployment_id=2,
                created_at=now,
            ),
            store,
        )

        # repo-y/staging: error 5h ago → success now → 5h MTTR
        failure_y = now - timedelta(hours=5)
        handle(
            _make_handle_payload(
                repo="mttr-isolation-test/repo-y",
                environment="staging",
                state="error",
                deployment_id=3,
                created_at=failure_y,
            ),
            store,
        )
        handle(
            _make_handle_payload(
                repo="mttr-isolation-test/repo-y",
                environment="staging",
                state="success",
                deployment_id=4,
                created_at=now,
            ),
            store,
        )

        mttr_x = self._read_gauge("mttr-isolation-test/repo-x", "production")
        mttr_y = self._read_gauge("mttr-isolation-test/repo-y", "staging")

        assert mttr_x == pytest.approx(2.0, abs=0.1)
        assert mttr_y == pytest.approx(5.0, abs=0.1)


# ---------------------------------------------------------------------------
# Module structure tests — ensure dora.mttr can be imported
# ---------------------------------------------------------------------------


class TestMttrModuleStructure:
    """The dora.mttr module must be discoverable and well-formed."""

    def test_dora_mttr_module_is_importable(self):
        """import dora.mttr must succeed."""
        import dora.mttr  # noqa: F401

    def test_calculate_mttr_is_callable(self):
        """calculate_mttr must be a callable exported from the module."""
        from dora.mttr import calculate_mttr

        assert callable(calculate_mttr)

    def test_mttr_gauge_constant_exists(self):
        """MTTR_GAUGE must be exported from the module."""
        from dora.mttr import MTTR_GAUGE

        assert MTTR_GAUGE is not None

    def test_function_signature_accepts_repo_environment_store_now(self):
        """calculate_mttr must accept (repo, environment, store, now)."""
        import inspect

        from dora.mttr import calculate_mttr

        sig = inspect.signature(calculate_mttr)
        param_names = list(sig.parameters.keys())

        assert param_names == ["repo", "environment", "store", "now"]
