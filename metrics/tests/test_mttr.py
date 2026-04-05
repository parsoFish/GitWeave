"""Unit tests for DORA Mean Time to Restore (MTTR) metric computation.

MTTR: median seconds from a failed deployment_status event to the next
successful deployment_status event for the same repository.

Algorithm:
  1. Collect all deployment_status events in the rolling 30-day window for
     the given repo.
  2. Sort events chronologically by created_at.
  3. For each event with state in ('failure', 'error'), find the **next**
     event with state='success' in the same repository.
  4. Compute the recovery time as (success.created_at - failure.created_at).total_seconds().
  5. Return the **median** across all resolved incidents.
  6. Incidents with no subsequent recovery within the query window are
     excluded from the median (unresolved = outside window).
  7. Return 0.0 when there are no failed deployments (or no resolvable incidents).

All tests use InMemoryEventStore and in-memory fixtures — no I/O.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

_REPO = "owner/repo"
_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_WINDOW_DAYS = 30


def _deployment_event(
    repo: str = _REPO,
    state: str = "success",
    created_at: datetime | None = None,
    environment: str = "production",
    deployment_id: int = 1,
) -> dict[str, Any]:
    """Build a minimal deployment_status event dict."""
    return {
        "event_type": "deployment_status",
        "repo": repo,
        "state": state,
        "environment": environment,
        "deployment_id": deployment_id,
        "created_at": created_at if created_at is not None else _NOW,
    }


def _store_with_events(events: list[dict[str, Any]]) -> Any:
    """Return an InMemoryEventStore pre-loaded with the given events."""
    from store import InMemoryEventStore

    store = InMemoryEventStore()
    for event in events:
        store.store_event(event)
    return store


# ---------------------------------------------------------------------------
# Import the function under test (will fail until implementation exists)
# ---------------------------------------------------------------------------


def _import_calculate_mttr():
    from dora.mttr import calculate_mttr  # noqa: PLC0415

    return calculate_mttr


# ---------------------------------------------------------------------------
# Tests: no failures → return 0.0
# ---------------------------------------------------------------------------


class TestNoFailures:
    """When there are no failed deployments, MTTR must return 0.0."""

    def test_empty_store_returns_zero(self):
        calculate_mttr = _import_calculate_mttr()
        store = _store_with_events([])
        result = calculate_mttr(_REPO, store, _NOW)
        assert result == 0.0

    def test_only_successful_deployments_returns_zero(self):
        calculate_mttr = _import_calculate_mttr()
        events = [
            _deployment_event(state="success", created_at=_NOW - timedelta(days=1)),
            _deployment_event(state="success", created_at=_NOW - timedelta(days=2)),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        assert result == 0.0

    def test_only_pending_deployments_returns_zero(self):
        calculate_mttr = _import_calculate_mttr()
        events = [
            _deployment_event(state="pending", created_at=_NOW - timedelta(days=1)),
            _deployment_event(state="in_progress", created_at=_NOW - timedelta(days=2)),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Tests: single failure → recovery pair
# ---------------------------------------------------------------------------


class TestSingleIncident:
    """A single failure followed by a success produces the correct recovery time."""

    def test_single_failure_then_success(self):
        calculate_mttr = _import_calculate_mttr()
        failure_time = _NOW - timedelta(hours=4)
        recovery_time = _NOW - timedelta(hours=2)
        events = [
            _deployment_event(state="failure", created_at=failure_time, deployment_id=10),
            _deployment_event(state="success", created_at=recovery_time, deployment_id=11),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        expected = timedelta(hours=2).total_seconds()
        assert result == pytest.approx(expected)

    def test_error_state_treated_as_failure(self):
        """'error' state should count as an incident that needs recovery."""
        calculate_mttr = _import_calculate_mttr()
        failure_time = _NOW - timedelta(hours=6)
        recovery_time = _NOW - timedelta(hours=3)
        events = [
            _deployment_event(state="error", created_at=failure_time, deployment_id=20),
            _deployment_event(state="success", created_at=recovery_time, deployment_id=21),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        expected = timedelta(hours=3).total_seconds()
        assert result == pytest.approx(expected)

    def test_recovery_time_uses_next_success_not_subsequent_failure(self):
        """The recovery pairs with the NEXT success, not any later failure."""
        calculate_mttr = _import_calculate_mttr()
        failure_time = _NOW - timedelta(hours=8)
        success_time = _NOW - timedelta(hours=6)
        second_failure_time = _NOW - timedelta(hours=4)
        events = [
            _deployment_event(state="failure", created_at=failure_time, deployment_id=30),
            _deployment_event(state="success", created_at=success_time, deployment_id=31),
            _deployment_event(state="failure", created_at=second_failure_time, deployment_id=32),
        ]
        store = _store_with_events(events)
        # Second failure has no subsequent success, so only the first incident is resolved.
        result = calculate_mttr(_REPO, store, _NOW)
        expected = timedelta(hours=2).total_seconds()
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests: multiple incidents → median
# ---------------------------------------------------------------------------


class TestMultipleIncidents:
    """Multiple resolved incidents: MTTR is the median of recovery times."""

    def test_two_incidents_returns_median(self):
        calculate_mttr = _import_calculate_mttr()
        # Incident 1: 1-hour recovery
        f1 = _NOW - timedelta(hours=10)
        r1 = _NOW - timedelta(hours=9)  # 1 hour
        # Incident 2: 3-hour recovery
        f2 = _NOW - timedelta(hours=6)
        r2 = _NOW - timedelta(hours=3)  # 3 hours
        events = [
            _deployment_event(state="failure", created_at=f1, deployment_id=40),
            _deployment_event(state="success", created_at=r1, deployment_id=41),
            _deployment_event(state="failure", created_at=f2, deployment_id=42),
            _deployment_event(state="success", created_at=r2, deployment_id=43),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        # Median of [3600, 10800] = (3600 + 10800) / 2 = 7200
        expected = 7200.0
        assert result == pytest.approx(expected)

    def test_three_incidents_returns_middle_value(self):
        calculate_mttr = _import_calculate_mttr()
        # Recovery times: 1h, 2h, 3h → median = 2h
        base = _NOW - timedelta(hours=20)
        events = [
            # Incident 1: 1-hour recovery
            _deployment_event(state="failure", created_at=base, deployment_id=50),
            _deployment_event(state="success", created_at=base + timedelta(hours=1), deployment_id=51),
            # Incident 2: 2-hour recovery
            _deployment_event(state="failure", created_at=base + timedelta(hours=3), deployment_id=52),
            _deployment_event(state="success", created_at=base + timedelta(hours=5), deployment_id=53),
            # Incident 3: 3-hour recovery
            _deployment_event(state="failure", created_at=base + timedelta(hours=7), deployment_id=54),
            _deployment_event(state="success", created_at=base + timedelta(hours=10), deployment_id=55),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        expected = timedelta(hours=2).total_seconds()
        assert result == pytest.approx(expected)

    def test_mixed_failure_and_error_states(self):
        """Both 'failure' and 'error' states contribute to MTTR."""
        calculate_mttr = _import_calculate_mttr()
        f1 = _NOW - timedelta(hours=8)
        r1 = _NOW - timedelta(hours=7)  # 1 hour recovery
        f2 = _NOW - timedelta(hours=5)
        r2 = _NOW - timedelta(hours=3)  # 2 hours recovery
        events = [
            _deployment_event(state="failure", created_at=f1, deployment_id=60),
            _deployment_event(state="success", created_at=r1, deployment_id=61),
            _deployment_event(state="error", created_at=f2, deployment_id=62),
            _deployment_event(state="success", created_at=r2, deployment_id=63),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        expected = (3600 + 7200) / 2  # median of [3600, 7200]
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests: unresolved incidents at window end are excluded
# ---------------------------------------------------------------------------


class TestUnresolvedIncidents:
    """Failures with no subsequent success are excluded from the median."""

    def test_unresolved_incident_excluded_from_median(self):
        calculate_mttr = _import_calculate_mttr()
        # One resolved incident (2-hour recovery) and one unresolved incident
        f1 = _NOW - timedelta(hours=8)
        r1 = _NOW - timedelta(hours=6)  # 2 hours
        f2 = _NOW - timedelta(hours=2)  # No subsequent success → unresolved
        events = [
            _deployment_event(state="failure", created_at=f1, deployment_id=70),
            _deployment_event(state="success", created_at=r1, deployment_id=71),
            _deployment_event(state="failure", created_at=f2, deployment_id=72),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        # Only the resolved incident counts: median of [7200] = 7200
        expected = timedelta(hours=2).total_seconds()
        assert result == pytest.approx(expected)

    def test_all_incidents_unresolved_returns_zero(self):
        calculate_mttr = _import_calculate_mttr()
        events = [
            _deployment_event(state="failure", created_at=_NOW - timedelta(hours=5), deployment_id=80),
            _deployment_event(state="failure", created_at=_NOW - timedelta(hours=3), deployment_id=81),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        assert result == 0.0

    def test_success_before_failure_does_not_resolve_it(self):
        """A success that occurred BEFORE a failure cannot be its recovery."""
        calculate_mttr = _import_calculate_mttr()
        success_time = _NOW - timedelta(hours=6)  # Success happens BEFORE the failure
        failure_time = _NOW - timedelta(hours=4)  # Failure is unresolved
        events = [
            _deployment_event(state="success", created_at=success_time, deployment_id=90),
            _deployment_event(state="failure", created_at=failure_time, deployment_id=91),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        # The failure has no subsequent success → excluded → returns 0.0
        assert result == 0.0


# ---------------------------------------------------------------------------
# Tests: window boundary behaviour
# ---------------------------------------------------------------------------


class TestWindowBoundary:
    """Only events within the 30-day rolling window are considered."""

    def test_events_outside_window_are_ignored(self):
        calculate_mttr = _import_calculate_mttr()
        # Failure outside 30-day window — should be ignored
        old_failure = _NOW - timedelta(days=31)
        old_recovery = _NOW - timedelta(days=30, hours=22)
        # Failure inside window
        recent_failure = _NOW - timedelta(days=5)
        recent_recovery = _NOW - timedelta(days=4)
        events = [
            _deployment_event(state="failure", created_at=old_failure, deployment_id=100),
            _deployment_event(state="success", created_at=old_recovery, deployment_id=101),
            _deployment_event(state="failure", created_at=recent_failure, deployment_id=102),
            _deployment_event(state="success", created_at=recent_recovery, deployment_id=103),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        # Only recent incident counted
        expected = timedelta(days=1).total_seconds()
        assert result == pytest.approx(expected)

    def test_repo_isolation(self):
        """Events from different repositories must not affect each other's MTTR."""
        calculate_mttr = _import_calculate_mttr()
        other_repo = "owner/other-repo"
        # Other repo has a quick 30-minute recovery
        events = [
            _deployment_event(
                repo=other_repo,
                state="failure",
                created_at=_NOW - timedelta(hours=4),
                deployment_id=110,
            ),
            _deployment_event(
                repo=other_repo,
                state="success",
                created_at=_NOW - timedelta(hours=3, minutes=30),
                deployment_id=111,
            ),
            # Target repo has a 2-hour recovery
            _deployment_event(
                repo=_REPO,
                state="failure",
                created_at=_NOW - timedelta(hours=6),
                deployment_id=112,
            ),
            _deployment_event(
                repo=_REPO,
                state="success",
                created_at=_NOW - timedelta(hours=4),
                deployment_id=113,
            ),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        expected = timedelta(hours=2).total_seconds()
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests: return type
# ---------------------------------------------------------------------------


class TestReturnType:
    """calculate_mttr must always return a float."""

    def test_returns_float_on_zero(self):
        calculate_mttr = _import_calculate_mttr()
        store = _store_with_events([])
        result = calculate_mttr(_REPO, store, _NOW)
        assert isinstance(result, float)

    def test_returns_float_on_result(self):
        calculate_mttr = _import_calculate_mttr()
        events = [
            _deployment_event(state="failure", created_at=_NOW - timedelta(hours=3), deployment_id=120),
            _deployment_event(state="success", created_at=_NOW - timedelta(hours=1), deployment_id=121),
        ]
        store = _store_with_events(events)
        result = calculate_mttr(_REPO, store, _NOW)
        assert isinstance(result, float)
