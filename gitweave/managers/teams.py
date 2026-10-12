"""TeamsManager — create/update/delete GitHub org teams under GW_RESOURCE_PREFIX.

GW_RESOURCE_PREFIX is the primary ownership marker.  FORGE_RESOURCE_PREFIX is
optional; when set it must start with GW_RESOURCE_PREFIX and only narrows the
scope of managed resources to that sub-prefix.
"""
import os

from gitweave.managers.org import ResourceStatus


def _get_prefix() -> str:
    """Return the effective resource prefix.

    Uses GW_RESOURCE_PREFIX as the primary marker.  If FORGE_RESOURCE_PREFIX is
    also set it must start with GW_RESOURCE_PREFIX; otherwise EnvironmentError
    is raised naming FORGE_RESOURCE_PREFIX explicitly.
    """
    gw_prefix = os.environ.get("GW_RESOURCE_PREFIX", "")
    if not gw_prefix:
        raise EnvironmentError("GW_RESOURCE_PREFIX must be set and non-empty")
    forge_prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
    if forge_prefix:
        if not forge_prefix.startswith(gw_prefix):
            raise EnvironmentError(
                f"FORGE_RESOURCE_PREFIX ({forge_prefix!r}) must start with "
                f"GW_RESOURCE_PREFIX ({gw_prefix!r})"
            )
        return forge_prefix
    return gw_prefix


def _is_managed(name: str, prefix: str) -> bool:
    return name.startswith(prefix)


class TeamsManager:
    def __init__(self, gh_org):
        self._org = gh_org
        self._prefix = _get_prefix()

    def list_managed(self) -> list:
        return [t for t in self._org.get_teams() if _is_managed(t.name, self._prefix)]

    def apply(self, team_cfg: dict) -> ResourceStatus:
        name = team_cfg["name"]
        try:
            existing = {t.name: t for t in self._org.get_teams()}
            if name in existing:
                existing[name].edit(
                    name=name,
                    description=team_cfg.get("description", ""),
                    privacy=team_cfg.get("privacy", "closed"),
                )
            else:
                self._org.create_team(
                    name,
                    description=team_cfg.get("description", ""),
                    privacy=team_cfg.get("privacy", "closed"),
                )
            return ResourceStatus(name=name, status="ok")
        except Exception as exc:
            return ResourceStatus(name=name, status="error", error=str(exc))

    def delete(self, team_name: str) -> ResourceStatus:
        try:
            teams = {t.name: t for t in self._org.get_teams()}
            if team_name in teams:
                teams[team_name].delete()
            return ResourceStatus(name=team_name, status="ok")
        except Exception as exc:
            if "404" in str(exc):
                return ResourceStatus(name=team_name, status="ok")
            return ResourceStatus(name=team_name, status="error", error=str(exc))
