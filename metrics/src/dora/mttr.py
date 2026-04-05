"""DORA Mean Time to Restore (MTTR) metric computation.

MTTR: median seconds from a failed deployment_status event to the next
successful deployment_status event for the same repository.

Algorithm:
  1. Collect all deployment_status events in the rolling 30-day window.
  2. Sort events chronologically by created_at.
  3. For each event with state in ('failure', 'error'), find the next
     event with state='success' in the same repository.
  4. Compute recovery time as (success.created_at - failure.created_at).total_seconds().
  5. Return the median across all resolved incidents.
  6. Incidents with no subsequent recovery within the query window are excluded.
  7. Return 0.0 when there are no resolved incidents.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from store import EventStore

_WINDOW_DAYS = 30
_FAILURE_STATES = frozenset({"failure", "error"})


def calculate_mttr(
    repo: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Compute the mean time to restore for a repository.

    Args:
        repo:  GitHub repository full name (e.g. "octocat/Hello-World").
        store: EventStore to query for deployment_status events.
        now:   Reference datetime for the rolling 30-day window boundary.

    Returns:
        Median recovery time in seconds across all resolved incidents.
        Returns 0.0 when there are no failed deployments or no resolved incidents.
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    events = store.get_events(repo, "deployment_status", since_dt=window_start)

    sorted_events: list[dict[str, Any]] = sorted(
        events, key=lambda e: e["created_at"]
    )

    recovery_times: list[float] = []
    for i, event in enumerate(sorted_events):
        if event.get("state") not in _FAILURE_STATES:
            continue
        # Find the next success event after this failure
        for candidate in sorted_events[i + 1 :]:
            if candidate.get("state") == "success":
                delta = (
                    candidate["created_at"] - event["created_at"]
                ).total_seconds()
                recovery_times.append(delta)
                break

    if not recovery_times:
        return 0.0

    return float(statistics.median(recovery_times))
