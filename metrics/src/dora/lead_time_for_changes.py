"""DORA Lead Time for Changes metric computation.

Lead Time for Changes: the median time (in seconds) from the earliest commit
push timestamp to PR merge per repository, measured over a rolling 30-day
window.

SHA correlation strategy:
  1. Query ``pull_request`` events where ``merged_at`` is not None.
  2. For each merged PR, look up its ``commit_sha`` in ``push`` events.
  3. Use the **earliest** commit timestamp in the matching push event.
  4. Compute ``(merged_at - earliest_commit_ts).total_seconds()``.
  5. Return the median across all resolved lead times.

PRs with no matching push event are excluded from the median.
Returns 0.0 when no resolvable merged PRs exist in the 30-day window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from store import EventStore

_WINDOW_DAYS = 30
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _earliest_commit_timestamp(
    repo: str,
    sha: str,
    store: "EventStore",
) -> datetime | None:
    """Return the earliest commit timestamp from the push event containing sha.

    Searches all push events for the given repo. When a push contains the
    target SHA, returns the minimum timestamp across all commits in that push.

    Returns None when the SHA cannot be found in any push event.
    """
    push_events = store.get_events(repo, "push", since_dt=_EPOCH)
    for event in push_events:
        commits: list[dict[str, Any]] = event.get("commits") or []
        if not any(c.get("sha") == sha for c in commits):
            continue
        timestamps: list[datetime] = []
        for c in commits:
            ts = c.get("timestamp")
            if ts is None:
                continue
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if isinstance(ts, datetime):
                timestamps.append(ts)
        if timestamps:
            return min(timestamps)
    return None


def calculate_lead_time_for_changes(
    repo: str,
    store: "EventStore",
    now: datetime,
) -> float:
    """Compute the median lead time for changes for a repository.

    Args:
        repo:  GitHub repository full name.
        store: EventStore to query for pull_request and push events.
        now:   Reference datetime for the rolling 30-day window boundary.

    Returns:
        Median lead time in seconds across merged PRs in the window whose
        commit SHA was found in a push event. Returns 0.0 when no resolvable
        merged PRs exist.
    """
    window_start = now - timedelta(days=_WINDOW_DAYS)
    pr_events = store.get_events(repo, "pull_request", since_dt=window_start)

    merged_prs = [
        e for e in pr_events if e.get("merged_at") is not None
    ]

    if not merged_prs:
        return 0.0

    lead_times: list[float] = []
    for event in merged_prs:
        sha = event.get("commit_sha")
        if not sha:
            continue
        merged_at = event.get("merged_at")
        if merged_at is None:
            continue
        commit_ts = _earliest_commit_timestamp(repo, sha, store)
        if commit_ts is None:
            continue
        lead_times.append((merged_at - commit_ts).total_seconds())

    if not lead_times:
        return 0.0

    lead_times.sort()
    n = len(lead_times)
    if n % 2 == 1:
        return float(lead_times[n // 2])
    return float((lead_times[n // 2 - 1] + lead_times[n // 2]) / 2)
