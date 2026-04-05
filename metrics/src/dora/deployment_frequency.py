"""DORA Deployment Frequency metric computation.

Deployment Frequency: the daily rate of successful deployments to a given
environment over a rolling 30-day window.

Formula: count(state='success' deployments in last 30 days) / 30

Exposed as: gitweave_deployment_frequency_daily Prometheus Gauge
Labels: repository, environment
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, Gauge

if TYPE_CHECKING:
    from store import EventStore

_WINDOW_DAYS = 30

try:
    DEPLOYMENT_FREQUENCY_GAUGE: Any = Gauge(
        "gitweave_deployment_frequency_daily",
        "Daily rate of successful deployments per day (rolling 30-day window)",
        ["repository", "environment"],
    )
except ValueError:
    # Metric already registered — retrieve from global registry.
    # This happens when the module is reloaded during testing.
    DEPLOYMENT_FREQUENCY_GAUGE = REGISTRY._names_to_collectors.get(
        "gitweave_deployment_frequency_daily"
    )


def calculate_deployment_frequency(
    repo: str,
    environment: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Compute the deployment frequency for a repo+environment pair.

    Args:
        repo:        GitHub repository full name (e.g. "octocat/Hello-World").
        environment: Deployment target (e.g. "production").
        store:       EventStore to query for deployment_status events.
        now:         Reference datetime for the rolling 30-day window boundary.

    Returns:
        Float representing deployments per day (count / 30). Returns 0.0 when
        no successful deployments exist in the window.
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", since_dt=window_start)
    count = sum(
        1
        for e in events
        if e.get("state") == "success" and e.get("environment") == environment
    )
    return count / _WINDOW_DAYS
