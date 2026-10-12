"""ReposManager — create/update/delete GitHub org repos under GW_RESOURCE_PREFIX.

GW_RESOURCE_PREFIX is the primary ownership marker.  FORGE_RESOURCE_PREFIX is
optional; when set it must start with GW_RESOURCE_PREFIX and only narrows scope.
"""
import os

from gitweave.managers.org import ResourceStatus


def _get_prefix() -> str:
    """Return the effective resource prefix.

    Uses GW_RESOURCE_PREFIX as primary.  FORGE_RESOURCE_PREFIX, if set, must
    start with GW_RESOURCE_PREFIX; otherwise EnvironmentError names it.
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


class ReposManager:
    def __init__(self, gh_org):
        self._org = gh_org
        self._prefix = _get_prefix()

    def list_managed(self) -> list:
        return [r for r in self._org.get_repos() if _is_managed(r.name, self._prefix)]

    def apply(self, repo_cfg: dict) -> ResourceStatus:
        slug = repo_cfg["slug"]
        try:
            existing = {r.name: r for r in self._org.get_repos()}
            if slug in existing:
                existing[slug].edit(
                    description=repo_cfg.get("description", ""),
                    private=repo_cfg.get("private", True),
                    has_issues=repo_cfg.get("has_issues", True),
                    has_projects=repo_cfg.get("has_projects", True),
                )
            else:
                self._org.create_repo(
                    slug,
                    description=repo_cfg.get("description", ""),
                    private=repo_cfg.get("private", True),
                    has_issues=repo_cfg.get("has_issues", True),
                    has_projects=repo_cfg.get("has_projects", True),
                )
            return ResourceStatus(name=slug, status="ok")
        except Exception as exc:
            return ResourceStatus(name=slug, status="error", error=str(exc))

    def delete(self, slug: str) -> ResourceStatus:
        try:
            repos = {r.name: r for r in self._org.get_repos()}
            if slug in repos:
                repos[slug].delete()
            return ResourceStatus(name=slug, status="ok")
        except Exception as exc:
            if "404" in str(exc):
                return ResourceStatus(name=slug, status="ok")
            return ResourceStatus(name=slug, status="error", error=str(exc))
