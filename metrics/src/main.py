"""FastAPI application for GitWeave metrics observation and webhook event dispatch.

Replaces the original dummy metrics loop with a proper HTTP service exposing:
  - POST /webhook  — dispatches GitHub webhook events by X-GitHub-Event header
  - GET  /healthz  — liveness/readiness probe (always 200, no auth)
  - GET  /metrics  — Prometheus exposition format (no auth required)
"""

import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatible dummy metric — preserved so test_main.py keeps passing.
# Uses try/except to survive importlib.reload() calls in PORT env-var tests.
# ---------------------------------------------------------------------------
try:
    DUMMY_METRIC = Gauge("gitweave_dummy_metric", "A dummy metric for testing")
except ValueError:
    # Metric already registered (module reloaded via importlib.reload in tests).
    # Retrieve the existing collector from the default registry.
    DUMMY_METRIC = REGISTRY._names_to_collectors.get("gitweave_dummy_metric")

# ---------------------------------------------------------------------------
# Port configuration — integer so uvicorn accepts it directly.
# ---------------------------------------------------------------------------
PORT: int = int(os.environ.get("PORT", 8000))

# ---------------------------------------------------------------------------
# Supported GitHub event types for GitWeave
# ---------------------------------------------------------------------------
SUPPORTED_EVENTS: set[str] = {
    "push",
    "deployment",
    "deployment_status",
    "workflow_run",
    "release",
    "create",
}


# ---------------------------------------------------------------------------
# EventStore — injectable dependency for tracking processed events
# ---------------------------------------------------------------------------


class EventStore:
    """Lightweight in-process store for processed webhook events.

    Designed for dependency injection: tests inject a fresh store per test
    case via FastAPI's dependency_overrides mechanism, achieving full isolation
    without touching global state between tests.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        """Record a processed event without mutating the caller's payload."""
        self._records.append({"type": event_type, "payload": payload})

    def count(self) -> int:
        """Return the number of recorded events."""
        return len(self._records)

    def all(self) -> list[dict[str, Any]]:
        """Return a snapshot of all recorded events.

        Returns a new list so callers cannot mutate the internal store state.
        """
        return list(self._records)


# Module-level default store — shared across requests unless overridden via DI.
_default_store = EventStore()


def get_event_store() -> EventStore:
    """FastAPI dependency provider for the event store.

    Override via ``app.dependency_overrides[get_event_store]`` in tests to
    inject a fresh, isolated EventStore per test case.
    """
    return _default_store


# ---------------------------------------------------------------------------
# Dispatch logic — pure function, testable without HTTP layer
# ---------------------------------------------------------------------------


def dispatch_event(
    event_type: str,
    payload: dict[str, Any],
    store: EventStore,
) -> dict[str, Any]:
    """Route a GitHub webhook event to its handler.

    Returns a result dict with 'status', 'dispatched', and 'event' keys.

    Unsupported event types are handled gracefully — logged at DEBUG only,
    never WARNING or above. GitHub retries deliveries that receive non-2xx
    responses, so unsupported events must never raise exceptions or return
    error status.
    """
    if event_type in SUPPORTED_EVENTS:
        store.append(event_type, payload)
        logger.info("Dispatched supported event: %s", event_type)
        return {"status": "ok", "dispatched": True, "event": event_type}

    logger.debug("Received unsupported event type: %s — ignoring", event_type)
    return {"status": "ok", "dispatched": False, "event": event_type}


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="GitWeave Metrics & Webhook Service")


@app.post("/webhook")
async def webhook(
    payload: dict[str, Any],
    x_github_event: str | None = Header(default=None),
    store: EventStore = Depends(get_event_store),
) -> dict[str, Any]:
    """Receive and dispatch GitHub webhook events.

    Dispatches on the X-GitHub-Event header value. Unsupported event types
    return 200 (not 4xx) to prevent GitHub retry loops for unhandled types.
    A missing or empty header returns 400 — GitHub always sets this header,
    so its absence indicates a malformed request.
    """
    if not x_github_event:
        raise HTTPException(
            status_code=400,
            detail="Missing required X-GitHub-Event header",
        )
    return dispatch_event(x_github_event, payload, store)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Health check endpoint. Always returns 200 — no authentication required.

    Kubernetes liveness and readiness probes must always be able to reach this
    endpoint; gating it on auth or any application state would cause spurious
    pod restarts.
    """
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition format metrics endpoint.

    Serves all metrics from the default prometheus_client registry as
    text/plain in the standard Prometheus exposition format. No bearer token
    authentication is required (see acceptance criteria).
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Entry point — server only starts here, never at import time
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
