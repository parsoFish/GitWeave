"""gitweave.plan — diff engine for `gw plan`.

Compares declared config against a snapshot (fixture file or live org state)
and returns a structured PlanResult. Fixture mode makes zero network calls
even when GW_* environment variables are set.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Literal

from gitweave.auth import get_github_client
from gitweave.config import load_config

Action = Literal["create", "update", "delete", "unchanged"]


@dataclass
class PlanItem:
    resource_type: str   # "team", "repo", "ruleset", "org_settings"
    name: str
    action: Action
    detail: str = ""     # human-readable description of the change


@dataclass
class PlanResult:
    items: list[PlanItem] = field(default_factory=list)

    def print(self) -> None:
        """Print human-readable diff: + create, ~ update, - delete, = unchanged."""
        symbols = {"create": "+", "update": "~", "delete": "-", "unchanged": "="}
        for item in self.items:
            sym = symbols[item.action]
            print(
                f"  {sym} {item.resource_type}/{item.name}"
                + (f": {item.detail}" if item.detail else "")
            )


def _load_fixture(fixture_path: str) -> dict:
    return json.loads(pathlib.Path(fixture_path).read_text())


def _live_snapshot(gh_org: object, prefix: str) -> dict:
    """Build snapshot dict from live org (same shape as fixture)."""
    from gitweave.managers.teams import TeamsManager  # noqa: PLC0415

    return {
        "org_settings": {},
        "teams": [{"name": t.name} for t in TeamsManager(gh_org).list_managed()],
        "repos": [],
        "rulesets": [],
    }


def plan(fixture_path: str | None = None) -> PlanResult:
    """Compute diff.

    If *fixture_path* is given the fixture is used exclusively — no network
    calls are made regardless of any GW_* environment variables that may be
    set.  When *fixture_path* is None a live org snapshot is taken; GW_ORG
    must be set or EnvironmentError is raised.
    """
    cfg = load_config()
    prefix = os.environ.get("GW_RESOURCE_PREFIX", "")

    if fixture_path is not None:
        snapshot = _load_fixture(fixture_path)
    else:
        gw_org = os.environ.get("GW_ORG")
        if not gw_org:
            raise EnvironmentError(
                "GW_ORG is required for live plan (or use --fixture)"
            )
        gh = get_github_client()
        snapshot = _live_snapshot(gh.get_organization(gw_org), prefix)

    return _diff(cfg, snapshot, prefix)


def _resource_name(r: dict) -> str:
    """Extract the canonical name from a resource dict.

    Teams/rulesets have a top-level ``name`` key; repo overlays use
    ``metadata.name``.  Fallback to empty string so callers can filter
    safely with ``.startswith(prefix)``.
    """
    return r.get("name") or r.get("metadata", {}).get("name", "")


def _diff(cfg: dict, snapshot: dict, prefix: str) -> PlanResult:
    """Compare declared config against snapshot; return PlanResult."""
    result = PlanResult()

    declared_org = cfg["org_settings"]
    live_org = snapshot.get("org_settings", {})
    if declared_org != live_org:
        result.items.append(PlanItem("org_settings", "org_settings", "update"))
    else:
        result.items.append(PlanItem("org_settings", "org_settings", "unchanged"))

    # Plural key in config  →  singular resource_type label
    type_map = {"teams": "team", "repos": "repo", "rulesets": "ruleset"}

    for rtype, label in type_map.items():
        declared_names = {
            _resource_name(r)
            for r in cfg[rtype]
            if _resource_name(r).startswith(prefix)
        }
        declared_names.discard("")  # skip resources with no resolvable name
        snap_names = {
            _resource_name(r)
            for r in snapshot.get(rtype, [])
            if _resource_name(r).startswith(prefix)
        }
        snap_names.discard("")
        for n in sorted(declared_names - snap_names):
            result.items.append(PlanItem(label, n, "create"))
        for n in sorted(snap_names - declared_names):
            result.items.append(PlanItem(label, n, "delete"))
        for n in sorted(declared_names & snap_names):
            result.items.append(PlanItem(label, n, "unchanged"))

    # Self-serve resource types: no prefix filter (explicitly declared in policy).
    self_serve_type_map = {
        "self_serve_repos": "self_serve_repo",
        "policy_exceptions": "policy_exception",
        "team_memberships": "team_membership",
    }

    for rtype, label in self_serve_type_map.items():
        declared_names = {_resource_name(r) for r in cfg.get(rtype, [])}
        declared_names.discard("")
        snap_names = {_resource_name(r) for r in snapshot.get(rtype, [])}
        snap_names.discard("")
        for n in sorted(declared_names - snap_names):
            result.items.append(PlanItem(label, n, "create"))
        for n in sorted(snap_names - declared_names):
            result.items.append(PlanItem(label, n, "delete"))
        for n in sorted(declared_names & snap_names):
            result.items.append(PlanItem(label, n, "unchanged"))

    return result
