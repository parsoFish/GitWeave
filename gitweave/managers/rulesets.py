"""RulesetsManager — create/delete GitHub org rulesets under FORGE_RESOURCE_PREFIX.

PyGithub does not expose a high-level ruleset API, so we call the GitHub REST
API directly via the org's requester object (org._requester) or a plain requests
session using the installation token.  The requester approach avoids adding a
hard dependency on `requests` here.
"""
import os

from gitweave.managers.org import ResourceStatus


def _get_prefix() -> str:
    prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
    if not prefix:
        raise EnvironmentError("FORGE_RESOURCE_PREFIX must be set and non-empty")
    return prefix


def _is_managed(name: str, prefix: str) -> bool:
    return name.startswith(prefix)


class RulesetsManager:
    def __init__(self, gh_org):
        self._org = gh_org
        self._prefix = _get_prefix()

    def list_managed(self) -> list:
        """Return rulesets whose name starts with FORGE_RESOURCE_PREFIX."""
        _, data = self._org._requester.requestJsonAndCheck(
            "GET",
            f"/orgs/{self._org.login}/rulesets",
        )
        return [r for r in (data or []) if _is_managed(r.get("name", ""), self._prefix)]

    def apply(self, ruleset_cfg: dict) -> ResourceStatus:
        """Create or update a ruleset; return ResourceStatus."""
        name = ruleset_cfg["name"]
        try:
            existing = {r["name"]: r for r in self.list_managed()}
            if name in existing:
                ruleset_id = existing[name]["id"]
                self._org._requester.requestJsonAndCheck(
                    "PUT",
                    f"/orgs/{self._org.login}/rulesets/{ruleset_id}",
                    input=ruleset_cfg,
                )
            else:
                self._org._requester.requestJsonAndCheck(
                    "POST",
                    f"/orgs/{self._org.login}/rulesets",
                    input=ruleset_cfg,
                )
            return ResourceStatus(name=name, status="ok")
        except Exception as exc:
            return ResourceStatus(name=name, status="error", error=str(exc))

    def delete(self, name: str) -> ResourceStatus:
        """Delete a ruleset by name; treat 404 as success."""
        try:
            existing = {r["name"]: r for r in self.list_managed()}
            if name in existing:
                ruleset_id = existing[name]["id"]
                self._org._requester.requestJsonAndCheck(
                    "DELETE",
                    f"/orgs/{self._org.login}/rulesets/{ruleset_id}",
                )
            return ResourceStatus(name=name, status="ok")
        except Exception as exc:
            if "404" in str(exc):
                return ResourceStatus(name=name, status="ok")
            return ResourceStatus(name=name, status="error", error=str(exc))
