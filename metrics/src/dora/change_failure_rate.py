"""DORA Change Failure Rate metric.

Change Failure Rate: the proportion of deployments in the last 30 days that
resulted in a production failure.

Exposed as: gitweave_change_failure_rate Prometheus Gauge (0.0–1.0)
Labels: repository, environment
Formula:
  numerator   = count(state='failure' OR state='error' in last 30 days)
  denominator = count(state='success' OR state='failure' OR state='error' in last 30 days)
  CFR         = numerator / denominator   (0.0 when denominator == 0)

States 'pending' and 'in_progress' are excluded from BOTH numerator and denominator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from prometheus_client import Gauge

if TYPE_CHECKING:
    from store import EventStore

CHANGE_FAILURE_RATE_GAUGE = Gauge(
    "gitweave_change_failure_rate",
    "Proportion of deployments in the last 30 days that resulted in a production failure",
    ["repository", "environment"],
)

_WINDOW_DAYS = 30
_FAILURE_STATES = frozenset({"failure", "error"})
_COUNTED_STATES = frozenset({"success", "failure", "error"})


def calculate_change_failure_rate(
    repo: str,
    environment: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Calculate the change failure rate for a given repo and environment.

    Counts deployment_status events within the last 30 days (inclusive of
    exactly 30 days ago). Only success, failure, and error states are counted;
    pending and in_progress are excluded from both numerator and denominator.

    Args:
        repo:        Repository full name (e.g. 'octocat/Hello-World').
        environment: Deployment environment (e.g. 'production').
        store:       EventStore to query for historical events.
        now:         Reference point for the 30-day window.

    Returns:
        Float in [0.0, 1.0] representing the proportion of failed deployments.
        Returns 0.0 when there are no counted deployments (no ZeroDivisionError).
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", window_start)

    denominator = 0
    numerator = 0

    for e in events:
        if e.get("environment") != environment:
            continue
        state = e.get("state")
        if state not in _COUNTED_STATES:
            continue
        denominator += 1
        if state in _FAILURE_STATES:
            numerator += 1

    if denominator == 0:
        return 0.0

    return numerator / denominator


def update_change_failure_rate_gauge(
    repo: str,
    environment: str,
    store: "EventStore",
) -> None:
    """Recalculate and update the Prometheus gauge for the given repo+environment.

    Called synchronously after each deployment_status event is stored so the
    gauge always reflects the current change failure rate.
    """
    now = datetime.now(tz=timezone.utc)
    cfr = calculate_change_failure_rate(repo, environment, store, now)
    CHANGE_FAILURE_RATE_GAUGE.labels(
        repository=repo,
        environment=environment,
    ).set(cfr)
