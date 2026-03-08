"""DORA Mean Time to Restore (MTTR) metric.

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
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from prometheus_client import Gauge

if TYPE_CHECKING:
    from store import EventStore

MTTR_GAUGE = Gauge(
    "gitweave_mttr_hours",
    "Median time to restore from production failures in the last 30 days (hours)",
    ["repository", "environment"],
)

_WINDOW_DAYS = 30
_FAILURE_STATES = frozenset({"failure", "error"})


def calculate_mttr(
    repo: str,
    environment: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Calculate the mean time to restore for a given repo and environment.

    Walks deployment_status events chronologically to find failure→recovery
    pairs. Consecutive failures before a recovery use only the last failure as
    the pair start. Unpaired failures (no subsequent success in the window) are
    excluded. Returns the median restore duration in hours, or 0.0 if no pairs.

    Args:
        repo:        Repository full name (e.g. 'octocat/Hello-World').
        environment: Deployment environment (e.g. 'production').
        store:       EventStore to query for historical events.
        now:         Reference point for the 30-day window.

    Returns:
        Median restore duration in hours (float). Returns 0.0 when there are
        no complete failure→recovery pairs in the window.
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", window_start)

    # Filter to this environment and sort chronologically
    env_events = sorted(
        (e for e in events if e.get("environment") == environment),
        key=lambda e: e["created_at"],
    )

    durations_hours: list[float] = []
    current_failure: datetime | None = None

    for event in env_events:
        state = event.get("state")
        created_at: datetime = event["created_at"]

        if state in _FAILURE_STATES:
            # Track the last failure before a recovery; consecutive failures
            # overwrite the previous one so only the last counts.
            current_failure = created_at
        elif state == "success" and current_failure is not None:
            # Pair found: measure duration from last failure to this recovery.
            duration_hours = (created_at - current_failure).total_seconds() / 3600
            durations_hours.append(duration_hours)
            # Reset: this success resolves the failure streak.
            current_failure = None

    if not durations_hours:
        return 0.0

    return _median(durations_hours)


def _median(values: list[float]) -> float:
    """Return the median of a non-empty list of floats."""
    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2


def update_mttr_gauge(
    repo: str,
    environment: str,
    store: "EventStore",
) -> None:
    """Recalculate and update the Prometheus gauge for the given repo+environment.

    Called synchronously after each deployment_status event is stored so the
    gauge always reflects the current MTTR.
    """
    now = datetime.now(tz=timezone.utc)
    mttr = calculate_mttr(repo, environment, store, now)
    MTTR_GAUGE.labels(
        repository=repo,
        environment=environment,
    ).set(mttr)
