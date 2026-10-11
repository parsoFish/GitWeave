# gitweave/managers/org.py
from dataclasses import dataclass, field
from typing import Literal

ORG_DEFAULTS = {
    "description": "",
    "default_repository_permission": "read",
    "web_commit_signoff_required": False,
    "members_can_create_repositories": True,
}


@dataclass
class ResourceStatus:
    name: str
    status: Literal["ok", "error", "skipped"]
    error: str | None = None


class OrgSettingsManager:
    def __init__(self, gh_org):
        """gh_org: PyGithub Organization object (from Github.get_organization(GW_ORG))."""
        self._org = gh_org

    def current(self) -> dict:
        """Return current live org settings as a dict."""
        return {
            "description": self._org.description or "",
            "default_repository_permission": self._org.default_repository_permission,
            "web_commit_signoff_required": self._org.web_commit_signoff_required,
            "members_can_create_repositories": self._org.members_can_create_repositories,
        }

    def apply(self, desired: dict) -> ResourceStatus:
        """Apply org settings via PATCH /orgs/{org}; return ResourceStatus.

        Uses the requester directly because PyGithub's Organization.edit()
        only exposes a limited subset of fields (description, blog, …) and
        does not support default_repository_permission, web_commit_signoff_required
        or members_can_create_repositories.
        """
        try:
            self._org._requester.requestJsonAndCheck(
                "PATCH", self._org.url, input=desired
            )
            return ResourceStatus(name="org_settings", status="ok")
        except Exception as exc:
            return ResourceStatus(name="org_settings", status="error", error=str(exc))

    def reset(self) -> ResourceStatus:
        """Restore org settings to GitHub safe defaults."""
        return self.apply(ORG_DEFAULTS)
