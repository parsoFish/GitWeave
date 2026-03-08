"""Startup replay: backfill the event store from the GitHub Events API.

On first start with an empty database, fetches the last 24 hours of events
from the GitHub Events API for each configured repository, parses PushEvent,
PullRequestEvent (merged only), and DeploymentStatusEvent payloads, and stores
them using the EventStore interface.

The HTTP layer is injected so tests can mock it without real network calls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable

import requests

if TYPE_CHECKING:
    from store import EventStore

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_WINDOW_HOURS = 24


def _default_http_get(url: str, **kwargs: Any) -> requests.Response:
    return requests.get(url, **kwargs)


def startup_replay(
    store: "EventStore",
    github_token: str,
    repos: list[str],
    *,
    http_get: Callable[..., Any] = _default_http_get,
) -> int:
    """Backfill the event store with the last 24 hours of events from GitHub.

    Checks all configured repos first. If any repo already has events, the
    replay is skipped entirely. Otherwise fetches and stores events from the
    GitHub Events API for each repo.

    Args:
        store:        EventStore implementation to check and populate.
        github_token: GitHub personal access token for API authentication.
        repos:        List of repository full names (e.g. ['org/repo']).
        http_get:     HTTP GET callable — defaults to requests.get. Inject a
                      mock in tests to avoid real network calls.

    Returns:
        Total number of events stored (0 if replay was skipped).
    """
    if not repos:
        return 0

    # If any repo already has events, the store is not empty — skip entirely.
    since_epoch = datetime.min.replace(tzinfo=timezone.utc)
    for repo in repos:
        for event_type in ("push", "pull_request", "deployment_status"):
            if store.get_events(repo, event_type, since_epoch):
                logger.info("Event store is non-empty — skipping startup replay")
                return 0

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=_WINDOW_HOURS)
    headers = {"Authorization": f"Bearer {github_token}"}
    total_stored = 0

    for repo in repos:
        total_stored += _replay_repo(store, repo, cutoff, headers, http_get)

    logger.info("Startup replay stored %d events across %d repos", total_stored, len(repos))
    return total_stored


def _replay_repo(
    store: "EventStore",
    repo: str,
    cutoff: datetime,
    headers: dict[str, str],
    http_get: Callable[..., Any],
) -> int:
    """Fetch and store recent events for a single repository."""
    url = f"{_GITHUB_API_BASE}/repos/{repo}/events"
    try:
        response = http_get(url, headers=headers)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch events for %s: %s", repo, exc)
        return 0

    events = response.json()
    stored = 0
    for raw_event in events:
        parsed = _parse_event(raw_event, cutoff)
        if parsed is not None:
            store.store_event(parsed)
            stored += 1

    return stored


def _parse_event(raw: dict[str, Any], cutoff: datetime) -> dict[str, Any] | None:
    """Parse a raw GitHub Events API event into the internal event format.

    Returns None if the event should be skipped (wrong type, too old, not merged).
    """
    event_type = raw.get("type")
    created_at_str = raw.get("created_at", "")
    repo = raw.get("repo", {}).get("name", "")
    payload = raw.get("payload", {})

    try:
        created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

    if created_at < cutoff:
        return None

    if event_type == "PushEvent":
        return {
            "event_type": "push",
            "repo": repo,
            "ref": payload.get("ref", ""),
            "commits": payload.get("commits", []),
            "created_at": created_at,
        }

    if event_type == "PullRequestEvent":
        pr = payload.get("pull_request", {})
        if not pr.get("merged"):
            return None
        merged_at_str = pr.get("merged_at")
        try:
            merged_at = datetime.strptime(merged_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            merged_at = created_at
        return {
            "event_type": "pull_request",
            "repo": repo,
            "pr_number": pr.get("number"),
            "merge_commit_sha": pr.get("merge_commit_sha"),
            "merged_at": merged_at,
            "created_at": created_at,
        }

    if event_type == "DeploymentStatusEvent":
        status = payload.get("deployment_status", {})
        return {
            "event_type": "deployment_status",
            "repo": repo,
            "state": status.get("state"),
            "environment": status.get("environment"),
            "deployment_id": status.get("id"),
            "created_at": created_at,
        }

    return None
