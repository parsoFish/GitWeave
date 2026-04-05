"""DORA Change Failure Rate metric computation.

Change Failure Rate: the proportion of deployments in a rolling 30-day window
that resulted in a production failure (state='failure' or state='error').

Formula:
  numerator   = count(failure + error events in window)
  denominator = count(success + failure + error events in window)
  CFR         = numerator / denominator   (0.0 when denominator == 0)

States 'pending' and 'in_progress' are excluded from both numerator and
denominator — they represent in-flight work, not completed deployments.

Exposed as: gitweave_change_failure_rate Prometheus Gauge (range 0.0–1.0)
Labels: repository, environment
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, Gauge

if TYPE_CHECKING:
    from store import EventStore

_WINDOW_DAYS = 30
_FAILURE_STATES = frozenset({"failure", "error"})
_COUNTED_STATES = frozenset({"success", "failure", "error"})

try:
    CHANGE_FAILURE_RATE_GAUGE: Any = Gauge(
        "gitweave_change_failure_rate",
        "Proportion of deployments that resulted in failure (rolling 30-day window)",
        ["repository", "environment"],
    )
except ValueError:
    # Metric already registered — retrieve from global registry.
    CHANGE_FAILURE_RATE_GAUGE = REGISTRY._names_to_collectors.get(
        "gitweave_change_failure_rate"
    )


def calculate_change_failure_rate(
    repo: str,
    environment: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Compute the change failure rate for a repo+environment pair.

    Args:
        repo:        GitHub repository full name (e.g. "octocat/Hello-World").
        environment: Deployment target (e.g. "production").
        store:       EventStore to query for deployment_status events.
        now:         Reference datetime for the rolling 30-day window boundary.

    Returns:
        Float in [0.0, 1.0] representing the proportion of deployments that
        failed. Returns 0.0 when no countable deployments exist (avoids
        ZeroDivisionError).
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", since_dt=window_start)
    counted = [
        e
        for e in events
        if e.get("environment") == environment and e.get("state") in _COUNTED_STATES
    ]
    denominator = len(counted)
    if denominator == 0:
        return 0.0
    numerator = sum(1 for e in counted if e.get("state") in _FAILURE_STATES)
    return numerator / denominator
