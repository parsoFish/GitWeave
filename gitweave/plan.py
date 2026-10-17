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

import yaml

from gitweave.auth import get_github_client
from gitweave.config import load_config

Action = Literal["create", "update", "delete", "unchanged"]
OverlayAction = Literal["add", "unchanged", "skip"]


@dataclass
class PlanItem:
    resource_type: str   # "team", "repo", "ruleset", "org_settings"
    name: str
    action: Action
    detail: str = ""     # human-readable description of the change


@dataclass
class OverlayPlanItem:
    repo_name: str
    action: OverlayAction
    module_name: str = ""
    module_version: str = ""
    file_count: int = 0

    def format_line(self) -> str:
        if self.action == "add":
            ver = f" @ {self.module_version}" if self.module_version else ""
            files = f" ({self.file_count} files)" if self.file_count else ""
            return f"  {self.repo_name}: would add [{self.module_name}{ver}]{files}"
        if self.action == "unchanged":
            ver = f" @ {self.module_version}" if self.module_version else ""
            return f"  {self.repo_name}: unchanged ({self.module_name}{ver})"
        return f"  {self.repo_name}: skip (no modules declared)"


@dataclass
class PlanResult:
    items: list[PlanItem] = field(default_factory=list)
    overlay_items: list[OverlayPlanItem] = field(default_factory=list)

    def print(self) -> None:
        """Print human-readable diff: + create, ~ update, - delete, = unchanged."""
        symbols = {"create": "+", "update": "~", "delete": "-", "unchanged": "="}
        for item in self.items:
            sym = symbols[item.action]
            print(
                f"  {sym} {item.resource_type}/{item.name}"
                + (f": {item.detail}" if item.detail else "")
            )
        if self.overlay_items:
            print("Overlays:")
            for oi in self.overlay_items:
                print(oi.format_line())


_MODULES_ROOT = pathlib.Path(__file__).parent.parent / "modules"
_REPOS_CONFIG_ROOT = pathlib.Path(__file__).parent.parent / "config" / "repos"


_EMPTY_SNAPSHOT: dict = {
    "org_settings": {
        "description": "",
        "default_repository_permission": "read",
        "web_commit_signoff_required": False,
        "members_can_create_repositories": True,
    },
    "teams": [],
    "repos": [],
    "rulesets": [],
}


def _load_fixture(fixture_path: str) -> dict:
    raw = json.loads(pathlib.Path(fixture_path).read_text())
    # Fill defaults so overlay-only fixtures work with _diff()
    merged = {**_EMPTY_SNAPSHOT, **raw}
    return merged


def _module_file_count(module_name: str) -> int:
    """Count renderable (non-copier-meta) files in a module directory."""
    mod_dir = _MODULES_ROOT / module_name
    if not mod_dir.exists():
        return 0
    return sum(
        1 for p in mod_dir.rglob("*")
        if p.is_file() and p.name != "copier.yaml"
    )


def _module_version(module_name: str) -> str:
    """Return the version declared in modules/<name>/copier.yaml, or ''."""
    copier_yaml = _MODULES_ROOT / module_name / "copier.yaml"
    if not copier_yaml.exists():
        return ""
    data = yaml.safe_load(copier_yaml.read_text())
    return data.get("_metadata", {}).get("version", "")


def _repo_declared_modules(repo_name: str) -> list[str]:
    """Return list of module names declared in config/repos/<repo_name>.yaml.

    Searches for a yaml file whose ``metadata.name`` matches *repo_name*, or
    whose filename stem matches (for simple name-based lookup).  Returns []
    when not found.
    """
    if not _REPOS_CONFIG_ROOT.exists():
        return []
    for yaml_file in _REPOS_CONFIG_ROOT.glob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_file.read_text()) or {}
        except Exception:  # noqa: BLE001
            continue
        name = data.get("metadata", {}).get("name", yaml_file.stem)
        if name == repo_name:
            return [m["name"] for m in data.get("spec", {}).get("modules", [])]
    return []


def _diff_overlays(fixture_repos: list[dict]) -> list[OverlayPlanItem]:
    """Compare fixture overlay state against declared modules; return items."""
    overlay_items: list[OverlayPlanItem] = []
    for repo in fixture_repos:
        repo_name = repo.get("name", "")
        declared = _repo_declared_modules(repo_name)
        if not declared:
            continue  # no modules declared → skip
        applied = repo.get("overlay")  # None = no overlay applied
        if applied is None:
            # No overlay applied yet; would add the first declared module
            module_name = declared[0]
            overlay_items.append(
                OverlayPlanItem(
                    repo_name=repo_name,
                    action="add",
                    module_name=module_name,
                    module_version=_module_version(module_name),
                    file_count=_module_file_count(module_name),
                )
            )
        else:
            # Overlay applied; check if it matches declared
            applied_module = applied.get("_module_name", "")
            applied_version = applied.get("_module_version", "")
            overlay_items.append(
                OverlayPlanItem(
                    repo_name=repo_name,
                    action="unchanged",
                    module_name=applied_module,
                    module_version=applied_version,
                )
            )
    return overlay_items


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

    result = _diff(cfg, snapshot, prefix)

    if fixture_path is not None:
        fixture_repos = snapshot.get("repos", [])
        overlay_repos = [r for r in fixture_repos if "overlay" in r]
        if overlay_repos:
            result.overlay_items = _diff_overlays(overlay_repos)

    return result


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
