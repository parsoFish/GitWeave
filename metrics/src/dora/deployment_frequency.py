"""DORA Deployment Frequency metric.

Deployment Frequency: the daily rate of successful deployments to production
over a rolling 30-day window.

Exposed as: gitweave_deployment_frequency_daily Prometheus Gauge
Labels: repository, environment
Formula: count(successful deployment_status events in last 30 days) / 30
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from prometheus_client import Gauge

if TYPE_CHECKING:
    from store import EventStore

DEPLOYMENT_FREQUENCY_GAUGE = Gauge(
    "gitweave_deployment_frequency_daily",
    "Daily rate of successful deployments to production over a rolling 30-day window",
    ["repository", "environment"],
)

_WINDOW_DAYS = 30


def calculate_deployment_frequency(
    repo: str,
    environment: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Calculate the daily deployment frequency for a given repo and environment.

    Counts successful deployment_status events within the last 30 days
    (inclusive of exactly 30 days ago) and divides by 30.

    Args:
        repo:        Repository full name (e.g. 'octocat/Hello-World').
        environment: Deployment environment (e.g. 'production').
        store:       EventStore to query for historical events.
        now:         Reference point for the 30-day window.

    Returns:
        Float representing average daily deployments (count / 30).
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", window_start)
    count = sum(
        1
        for e in events
        if e.get("environment") == environment and e.get("state") == "success"
    )
    return count / _WINDOW_DAYS


def update_deployment_frequency_gauge(
    repo: str,
    environment: str,
    store: "EventStore",
) -> None:
    """Recalculate and update the Prometheus gauge for the given repo+environment.

    Called synchronously after each deployment_status event is stored so the
    gauge always reflects the current rolling frequency.
    """
    now = datetime.now(tz=timezone.utc)
    frequency = calculate_deployment_frequency(repo, environment, store, now)
    DEPLOYMENT_FREQUENCY_GAUGE.labels(
        repository=repo,
        environment=environment,
    ).set(frequency)
