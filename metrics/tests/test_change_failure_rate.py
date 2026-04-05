"""Unit tests for DORA Change Failure Rate metric computation.

Tests are written in TDD style — they define the expected behaviour of
calculate_change_failure_rate() and the ChangeFailureRate Prometheus gauge
before (or alongside) implementation.

Formula under test:
    numerator   = count(state in {'failure', 'error'} events in last 30 days)
    denominator = count(state in {'success', 'failure', 'error'} events in last 30 days)
    CFR         = numerator / denominator   (0.0 when denominator == 0)

States 'pending' and 'in_progress' are excluded from both numerator and
denominator — they represent in-flight work, not completed deployments.

Scope: unit tests only. All store interactions use InMemoryEventStore or a
hand-rolled stub — no database, no network.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_WINDOW_DAYS = 30


def _make_event(
    repo: str = "org/repo",
    environment: str = "production",
    state: str = "success",
    days_ago: float = 1.0,
    now: datetime = _NOW,
) -> dict[str, Any]:
    """Return a minimal deployment_status event dict."""
    return {
        "event_type": "deployment_status",
        "repo": repo,
        "environment": environment,
        "state": state,
        "created_at": now - timedelta(days=days_ago),
    }


def _store_with_events(events: list[dict[str, Any]]) -> Any:
    """Return an InMemoryEventStore pre-loaded with the given events."""
    from store import InMemoryEventStore

    store = InMemoryEventStore()
    for e in events:
        store.store_event(e)
    return store


# ---------------------------------------------------------------------------
# TestChangeFailureRateZeroDeployments
# ---------------------------------------------------------------------------


class TestChangeFailureRateZeroDeployments:
    """calculate_change_failure_rate returns 0.0 when there are no countable deployments."""

    def test_returns_zero_for_empty_store(self):
        """An empty store must return 0.0 to avoid ZeroDivisionError."""
        from dora.change_failure_rate import calculate_change_failure_rate
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_when_no_events_for_repo(self):
        """Events for a different repo must not contribute to the result."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [_make_event(repo="other/repo", state="failure", days_ago=1)]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_when_no_events_in_window(self):
        """Events that fall before the 30-day window are not counted."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [_make_event(state="failure", days_ago=31)]  # One day outside the window
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_when_only_pending_events(self):
        """Pending events are excluded from both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="pending", days_ago=1),
                _make_event(state="pending", days_ago=2),
                _make_event(state="pending", days_ago=3),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_when_only_in_progress_events(self):
        """In-progress events are excluded from both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="in_progress", days_ago=1),
                _make_event(state="in_progress", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_when_events_are_for_wrong_environment(self):
        """Failure deployments to a different environment must not affect the result."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="staging", state="failure", days_ago=1),
                _make_event(environment="development", state="failure", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_return_value_is_float_for_empty_store(self):
        """Return value must be a float, even when the result is zero."""
        from dora.change_failure_rate import calculate_change_failure_rate
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# TestChangeFailureRateAllSuccess
# ---------------------------------------------------------------------------


class TestChangeFailureRateAllSuccess:
    """CFR is 0.0 when all counted deployments succeeded."""

    def test_single_success_event_returns_zero(self):
        """One successful deployment yields CFR of 0.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="success", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_multiple_success_events_return_zero(self):
        """Many successful deployments still yield CFR of 0.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        events = [_make_event(state="success", days_ago=float(i + 1)) for i in range(10)]
        store = _store_with_events(events)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_thirty_success_events_return_zero(self):
        """30 successful deployments (one per day) still yield CFR of 0.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        events = [_make_event(state="success", days_ago=float(i + 1)) for i in range(30)]
        store = _store_with_events(events)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_all_success_result_is_float(self):
        """Return value must be a float, not an integer, even for all-success case."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="success", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# TestChangeFailureRateAllFailure
# ---------------------------------------------------------------------------


class TestChangeFailureRateAllFailure:
    """CFR is 1.0 when all counted deployments failed."""

    def test_single_failure_event_returns_one(self):
        """One failed deployment with no successes yields CFR of 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="failure", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_single_error_event_returns_one(self):
        """One error deployment with no successes yields CFR of 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="error", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_multiple_failure_events_return_one(self):
        """Many failure events with no successes yield CFR of 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        events = [_make_event(state="failure", days_ago=float(i + 1)) for i in range(5)]
        store = _store_with_events(events)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_multiple_error_events_return_one(self):
        """Many error events with no successes yield CFR of 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        events = [_make_event(state="error", days_ago=float(i + 1)) for i in range(5)]
        store = _store_with_events(events)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_mixed_failure_and_error_events_return_one(self):
        """A mix of failure and error events with no successes yields CFR of 1.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="error", days_ago=2),
                _make_event(state="failure", days_ago=3),
                _make_event(state="error", days_ago=4),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_all_failure_result_is_float(self):
        """Return value must be a float, not an integer, even for all-failure case."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="failure", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# TestChangeFailureRateMixed
# ---------------------------------------------------------------------------


class TestChangeFailureRateMixed:
    """Verify CFR formula for mixed success/failure/error deployments."""

    def test_one_failure_one_success_returns_half(self):
        """1 failure out of 2 total deployments → CFR = 0.5."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)

    def test_one_error_one_success_returns_half(self):
        """1 error out of 2 total deployments → CFR = 0.5."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="error", days_ago=1),
                _make_event(state="success", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)

    def test_one_failure_three_successes_returns_one_quarter(self):
        """1 failure out of 4 total deployments → CFR = 0.25."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
                _make_event(state="success", days_ago=3),
                _make_event(state="success", days_ago=4),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.25)

    def test_three_failures_one_success_returns_three_quarters(self):
        """3 failures out of 4 total deployments → CFR = 0.75."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="failure", days_ago=2),
                _make_event(state="failure", days_ago=3),
                _make_event(state="success", days_ago=4),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.75)

    def test_two_failures_one_error_three_successes(self):
        """2 failures + 1 error out of 6 total → CFR = 0.5."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="failure", days_ago=2),
                _make_event(state="error", days_ago=3),
                _make_event(state="success", days_ago=4),
                _make_event(state="success", days_ago=5),
                _make_event(state="success", days_ago=6),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)

    def test_pending_events_do_not_affect_denominator(self):
        """Pending events are excluded from denominator; CFR uses only completed deployments."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
                _make_event(state="pending", days_ago=3),  # excluded
                _make_event(state="pending", days_ago=4),  # excluded
            ]
        )
        # 1 failure / (1 failure + 1 success) = 0.5, not 1/4
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)

    def test_in_progress_events_do_not_affect_denominator(self):
        """In-progress events are excluded from denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
                _make_event(state="in_progress", days_ago=3),  # excluded
            ]
        )
        # 1 failure / (1 failure + 1 success) = 0.5
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)

    def test_result_is_always_float(self):
        """Return value must be a float in all mixed scenarios."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)

    def test_result_is_within_zero_to_one(self):
        """CFR must always be in [0.0, 1.0]."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="error", days_ago=2),
                _make_event(state="success", days_ago=3),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert 0.0 <= result <= 1.0

    def test_large_dataset_formula_is_correct(self):
        """Verify formula accuracy over a large dataset: 7 failures out of 20 total."""
        from dora.change_failure_rate import calculate_change_failure_rate

        failures = [_make_event(state="failure", days_ago=float(i + 1)) for i in range(7)]
        successes = [_make_event(state="success", days_ago=float(i + 8)) for i in range(13)]
        store = _store_with_events(failures + successes)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(7 / 20)


# ---------------------------------------------------------------------------
# TestChangeFailureRateWindowBoundary
# ---------------------------------------------------------------------------


class TestChangeFailureRateWindowBoundary:
    """Rolling 30-day window uses >= semantics at the lower boundary."""

    def test_event_exactly_at_window_boundary_is_included(self):
        """An event at exactly now - 30 days falls on the boundary and must be counted."""
        from dora.change_failure_rate import calculate_change_failure_rate

        boundary_ts = _NOW - timedelta(days=_WINDOW_DAYS)
        event = {
            "event_type": "deployment_status",
            "repo": "org/repo",
            "environment": "production",
            "state": "failure",
            "created_at": boundary_ts,
        }
        store = _store_with_events([event])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_event_one_second_before_window_boundary_is_excluded(self):
        """An event one second before the 30-day boundary must not be counted."""
        from dora.change_failure_rate import calculate_change_failure_rate

        just_outside = _NOW - timedelta(days=_WINDOW_DAYS) - timedelta(seconds=1)
        event = {
            "event_type": "deployment_status",
            "repo": "org/repo",
            "environment": "production",
            "state": "failure",
            "created_at": just_outside,
        }
        store = _store_with_events([event])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_event_one_second_after_window_boundary_is_included(self):
        """An event just inside the 30-day boundary must be counted."""
        from dora.change_failure_rate import calculate_change_failure_rate

        just_inside = _NOW - timedelta(days=_WINDOW_DAYS) + timedelta(seconds=1)
        event = {
            "event_type": "deployment_status",
            "repo": "org/repo",
            "environment": "production",
            "state": "failure",
            "created_at": just_inside,
        }
        store = _store_with_events([event])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_event_in_future_is_included(self):
        """An event timestamped in the future relative to now is still within the window."""
        from dora.change_failure_rate import calculate_change_failure_rate

        future_event = {
            "event_type": "deployment_status",
            "repo": "org/repo",
            "environment": "production",
            "state": "failure",
            "created_at": _NOW + timedelta(hours=1),
        }
        store = _store_with_events([future_event])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_window_excludes_events_older_than_30_days(self):
        """Events from 31+ days ago must not affect CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        old_failure = _make_event(state="failure", days_ago=31)
        recent_success = _make_event(state="success", days_ago=1)
        store = _store_with_events([old_failure, recent_success])
        # Only the recent success is in window → 0 failures / 1 total = 0.0
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_window_is_exactly_30_days(self):
        """The window is exactly 30 days, not 29 or 31."""
        from dora.change_failure_rate import calculate_change_failure_rate

        # Event at exactly 30 days should be counted
        event_at_30 = _make_event(state="failure", days_ago=30.0)
        store = _store_with_events([event_at_30])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_now_parameter_controls_window_reference(self):
        """Passing an earlier 'now' shifts the lower window boundary to include older events.

        The store has no upper bound, so 'now' only affects what is OLD enough to be excluded.
        An earlier 'now' pushes the lower boundary back, capturing older events.
        """
        from dora.change_failure_rate import calculate_change_failure_rate

        past_now = _NOW - timedelta(days=10)
        # failure is 35 days before _NOW: outside _NOW window (35 > 30)
        # but inside past_now window: past_now - 30 = _NOW - 40, and 35 < 40 → included
        failure_event = _make_event(state="failure", days_ago=35, now=_NOW)
        success_event = _make_event(state="success", days_ago=5, now=_NOW)
        store = _store_with_events([failure_event, success_event])

        # With _NOW: failure is outside the 30-day window → 0 failures / 1 total = 0.0
        result_current = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result_current == 0.0

        # With past_now: window extends to _NOW - 40 days, capturing the old failure
        # → 1 failure / 2 total = 0.5
        result_past = calculate_change_failure_rate("org/repo", "production", store, past_now)
        assert result_past == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestChangeFailureRateEnvironmentFiltering
# ---------------------------------------------------------------------------


class TestChangeFailureRateEnvironmentFiltering:
    """CFR is scoped to a specific environment; other environments are ignored."""

    def test_production_cfr_excludes_staging_failures(self):
        """Staging failures must not increase the production CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="production", state="success", days_ago=1),
                _make_event(environment="staging", state="failure", days_ago=2),
                _make_event(environment="staging", state="failure", days_ago=3),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        # Only the production success is counted; staging failures are excluded
        assert result == 0.0

    def test_staging_cfr_excludes_production_failures(self):
        """Production failures must not increase the staging CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="staging", state="success", days_ago=1),
                _make_event(environment="production", state="failure", days_ago=2),
                _make_event(environment="production", state="failure", days_ago=3),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "staging", store, _NOW)
        # Only the staging success is counted
        assert result == 0.0

    def test_each_environment_has_independent_cfr(self):
        """production and staging CFRs are computed independently from the same store."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                # Production: 1 failure, 1 success → CFR = 0.5
                _make_event(environment="production", state="failure", days_ago=1),
                _make_event(environment="production", state="success", days_ago=2),
                # Staging: all successes → CFR = 0.0
                _make_event(environment="staging", state="success", days_ago=1),
                _make_event(environment="staging", state="success", days_ago=2),
            ]
        )
        prod_result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        staging_result = calculate_change_failure_rate("org/repo", "staging", store, _NOW)
        assert prod_result == pytest.approx(0.5)
        assert staging_result == 0.0

    def test_environment_filter_is_case_sensitive(self):
        """'Production' and 'production' are treated as different environments."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="Production", state="failure", days_ago=1),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        # The 'Production' event does not match the 'production' filter
        assert result == 0.0

    def test_empty_environment_string_is_filtered_independently(self):
        """An empty environment string is treated as a distinct environment value."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="", state="failure", days_ago=1),
                _make_event(environment="production", state="success", days_ago=2),
            ]
        )
        # Querying 'production' should not see the empty-env failure
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_development_environment_cfr_is_independent(self):
        """A third environment ('development') is also independently scoped."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(environment="production", state="success", days_ago=1),
                _make_event(environment="staging", state="failure", days_ago=1),
                _make_event(environment="development", state="failure", days_ago=1),
                _make_event(environment="development", state="failure", days_ago=2),
            ]
        )
        prod_result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        dev_result = calculate_change_failure_rate("org/repo", "development", store, _NOW)
        assert prod_result == 0.0
        assert dev_result == 1.0


# ---------------------------------------------------------------------------
# TestChangeFailureRateRepoFiltering
# ---------------------------------------------------------------------------


class TestChangeFailureRateRepoFiltering:
    """CFR is scoped to a specific repository; other repos are ignored."""

    def test_cfr_excludes_failures_from_other_repos(self):
        """Failures from other repositories must not affect the target repo's CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(repo="org/repo", state="success", days_ago=1),
                _make_event(repo="org/other", state="failure", days_ago=2),
                _make_event(repo="org/other", state="failure", days_ago=3),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_each_repo_has_independent_cfr(self):
        """Two repos computed from the same store must have independent CFR values."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                # repo-a: all failures → CFR = 1.0
                _make_event(repo="org/repo-a", state="failure", days_ago=1),
                _make_event(repo="org/repo-a", state="failure", days_ago=2),
                # repo-b: all successes → CFR = 0.0
                _make_event(repo="org/repo-b", state="success", days_ago=1),
                _make_event(repo="org/repo-b", state="success", days_ago=2),
            ]
        )
        result_a = calculate_change_failure_rate("org/repo-a", "production", store, _NOW)
        result_b = calculate_change_failure_rate("org/repo-b", "production", store, _NOW)
        assert result_a == 1.0
        assert result_b == 0.0

    def test_repo_filter_is_case_sensitive(self):
        """'Org/Repo' and 'org/repo' are treated as different repositories."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(repo="Org/Repo", state="failure", days_ago=1),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_returns_zero_for_repo_with_no_events(self):
        """A repo with zero events returns CFR of 0.0, not an error."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(repo="org/other-repo", state="failure", days_ago=1),
            ]
        )
        result = calculate_change_failure_rate("org/nonexistent-repo", "production", store, _NOW)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestChangeFailureRateStateClassification
# ---------------------------------------------------------------------------


class TestChangeFailureRateStateClassification:
    """Verify how each deployment state is classified for the formula."""

    def test_success_state_counts_in_denominator_only(self):
        """'success' increases denominator but not numerator → lower CFR."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="success", days_ago=1),
                _make_event(state="failure", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        # 1 failure / 2 total = 0.5
        assert result == pytest.approx(0.5)

    def test_failure_state_counts_in_numerator_and_denominator(self):
        """'failure' increases both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="failure", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        # 1 failure / 1 total = 1.0
        assert result == 1.0

    def test_error_state_counts_in_numerator_and_denominator(self):
        """'error' increases both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="error", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        # 1 error / 1 total = 1.0
        assert result == 1.0

    def test_pending_state_is_excluded_from_both(self):
        """'pending' is excluded from both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="pending", days_ago=1),
                _make_event(state="success", days_ago=2),
            ]
        )
        # pending is excluded → 0 failures / 1 success = 0.0
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_in_progress_state_is_excluded_from_both(self):
        """'in_progress' is excluded from both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="in_progress", days_ago=1),
                _make_event(state="failure", days_ago=2),
            ]
        )
        # in_progress is excluded → 1 failure / 1 total = 1.0
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_unknown_state_is_excluded(self):
        """An unrecognised state string is excluded from both numerator and denominator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="queued", days_ago=1),
                _make_event(state="waiting", days_ago=2),
                _make_event(state="success", days_ago=3),
            ]
        )
        # unknown states excluded → 0 failures / 1 success = 0.0
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 0.0

    def test_all_known_failure_states_are_treated_equally(self):
        """'failure' and 'error' are equivalent failure states in the numerator."""
        from dora.change_failure_rate import calculate_change_failure_rate

        # 1 failure + 1 error out of 4 total
        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="error", days_ago=2),
                _make_event(state="success", days_ago=3),
                _make_event(state="success", days_ago=4),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestChangeFailureRateReturnType
# ---------------------------------------------------------------------------


class TestChangeFailureRateReturnType:
    """Return value must always be a float in [0.0, 1.0]."""

    def test_return_type_is_float_for_zero_case(self):
        from dora.change_failure_rate import calculate_change_failure_rate
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)

    def test_return_type_is_float_for_one_case(self):
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events([_make_event(state="failure", days_ago=1)])
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)

    def test_return_type_is_float_for_fractional_case(self):
        from dora.change_failure_rate import calculate_change_failure_rate

        store = _store_with_events(
            [
                _make_event(state="failure", days_ago=1),
                _make_event(state="success", days_ago=2),
            ]
        )
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert isinstance(result, float)

    def test_result_is_never_negative(self):
        """CFR must be >= 0.0 in all scenarios."""
        from dora.change_failure_rate import calculate_change_failure_rate
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result >= 0.0

    def test_result_never_exceeds_one(self):
        """CFR must be <= 1.0 in all scenarios."""
        from dora.change_failure_rate import calculate_change_failure_rate

        events = [_make_event(state="failure", days_ago=float(i + 1)) for i in range(10)]
        store = _store_with_events(events)
        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# TestChangeFailureRatePrometheusGauge
# ---------------------------------------------------------------------------


class TestChangeFailureRatePrometheusGauge:
    """The module exposes a correctly named and labelled Prometheus gauge."""

    def test_gauge_is_importable(self):
        """CHANGE_FAILURE_RATE_GAUGE must be importable from the module."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert CHANGE_FAILURE_RATE_GAUGE is not None

    def test_gauge_name(self):
        """The gauge must be named 'gitweave_change_failure_rate'."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert CHANGE_FAILURE_RATE_GAUGE._name == "gitweave_change_failure_rate"

    def test_gauge_has_repository_label(self):
        """The gauge must have a 'repository' label dimension."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert "repository" in CHANGE_FAILURE_RATE_GAUGE._labelnames

    def test_gauge_has_environment_label(self):
        """The gauge must have an 'environment' label dimension."""
        from dora.change_failure_rate import CHANGE_FAILURE_RATE_GAUGE

        assert "environment" in CHANGE_FAILURE_RATE_GAUGE._labelnames

    def test_module_is_importable_without_side_effects(self):
        """Importing the module multiple times must not raise ValueError from duplicate metrics."""
        import importlib
        import sys

        # Remove cached module if present so we force a re-import
        mod_name = "dora.change_failure_rate"
        sys.modules.pop(mod_name, None)

        # Should not raise
        import dora.change_failure_rate  # noqa: F401

        assert "dora.change_failure_rate" in sys.modules


# ---------------------------------------------------------------------------
# TestChangeFailureRateStoreInterface
# ---------------------------------------------------------------------------


class TestChangeFailureRateStoreInterface:
    """calculate_change_failure_rate uses the EventStore protocol correctly."""

    def test_queries_deployment_status_event_type(self):
        """The function must query the store for 'deployment_status' events."""
        from dora.change_failure_rate import calculate_change_failure_rate

        mock_store = MagicMock()
        mock_store.get_events.return_value = []

        calculate_change_failure_rate("org/repo", "production", mock_store, _NOW)

        mock_store.get_events.assert_called_once()
        call_args = mock_store.get_events.call_args
        # Second positional arg (or 'event_type' kwarg) must be 'deployment_status'
        args, kwargs = call_args
        event_type = args[1] if len(args) > 1 else kwargs.get("event_type")
        assert event_type == "deployment_status"

    def test_queries_correct_repo(self):
        """The function must query the store with the provided repo name."""
        from dora.change_failure_rate import calculate_change_failure_rate

        mock_store = MagicMock()
        mock_store.get_events.return_value = []

        calculate_change_failure_rate("acme/my-service", "production", mock_store, _NOW)

        args, kwargs = mock_store.get_events.call_args
        repo = args[0] if args else kwargs.get("repo")
        assert repo == "acme/my-service"

    def test_queries_since_dt_is_30_days_before_now(self):
        """The window start passed to get_events must be exactly 30 days before now."""
        from dora.change_failure_rate import calculate_change_failure_rate

        mock_store = MagicMock()
        mock_store.get_events.return_value = []

        calculate_change_failure_rate("org/repo", "production", mock_store, _NOW)

        args, kwargs = mock_store.get_events.call_args
        since_dt = args[2] if len(args) > 2 else kwargs.get("since_dt")
        expected = _NOW - timedelta(days=30)
        assert since_dt == expected

    def test_works_with_in_memory_store(self):
        """The function works correctly with InMemoryEventStore (protocol compliance)."""
        from dora.change_failure_rate import calculate_change_failure_rate
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        store.store_event(_make_event(state="failure", days_ago=1))

        result = calculate_change_failure_rate("org/repo", "production", store, _NOW)
        assert result == 1.0

    def test_handles_store_returning_empty_list(self):
        """When the store returns an empty list, CFR must be 0.0."""
        from dora.change_failure_rate import calculate_change_failure_rate

        mock_store = MagicMock()
        mock_store.get_events.return_value = []

        result = calculate_change_failure_rate("org/repo", "production", mock_store, _NOW)
        assert result == 0.0

    def test_handles_events_missing_state_key(self):
        """Events without a 'state' key are treated as unknown state and excluded."""
        from dora.change_failure_rate import calculate_change_failure_rate

        # An event dict without the 'state' key
        mock_store = MagicMock()
        mock_store.get_events.return_value = [
            {
                "event_type": "deployment_status",
                "repo": "org/repo",
                "environment": "production",
                "created_at": _NOW - timedelta(days=1),
                # 'state' key deliberately absent
            }
        ]
        result = calculate_change_failure_rate("org/repo", "production", mock_store, _NOW)
        assert result == 0.0

    def test_handles_events_missing_environment_key(self):
        """Events without an 'environment' key are excluded by the environment filter."""
        from dora.change_failure_rate import calculate_change_failure_rate

        mock_store = MagicMock()
        mock_store.get_events.return_value = [
            {
                "event_type": "deployment_status",
                "repo": "org/repo",
                "state": "failure",
                "created_at": _NOW - timedelta(days=1),
                # 'environment' key deliberately absent
            }
        ]
        result = calculate_change_failure_rate("org/repo", "production", mock_store, _NOW)
        assert result == 0.0
