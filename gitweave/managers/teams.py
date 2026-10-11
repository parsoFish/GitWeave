"""TeamsManager — create/update/delete GitHub org teams under FORGE_RESOURCE_PREFIX."""
import os

from gitweave.managers.org import ResourceStatus


def _get_prefix() -> str:
    prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
    if not prefix:
        raise EnvironmentError("FORGE_RESOURCE_PREFIX must be set and non-empty")
    return prefix


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
