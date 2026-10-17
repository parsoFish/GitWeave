"""RulesetsManager — create/delete GitHub org rulesets under GW_RESOURCE_PREFIX.

GW_RESOURCE_PREFIX is the ownership marker for all gitweave-managed resources.

PyGithub does not expose a high-level ruleset API, so we call the GitHub REST
API directly via the org's requester object (org._requester) or a plain requests
session using the installation token.  The requester approach avoids adding a
hard dependency on `requests` here.
"""
import os

from gitweave.managers.org import ResourceStatus


_PLAN_LACKING_PHRASES = (
    "Upgrade to GitHub Team to enable this feature",
)


def _is_permission_denied(exc_data) -> tuple[bool, str | None]:
    """Check if a 403 body indicates a missing token permission (vs plan not supporting rulesets).

    Returns (is_permission_denied, permission_field_name).

    Permission-denied cases (should raise):
    - Body has ``errors`` list with ``code == "missing"`` entries (fine-grained token scopes).
    - Body ``message`` contains "Resource not accessible by integration" (classic token permission).

    Plan-lacking cases (should return [] / "unsupported"):
    - Body ``message`` contains "Upgrade to GitHub Team to enable this feature".
    """
    if not isinstance(exc_data, dict):
        return False, None
    message = exc_data.get("message", "")
    # Plan-lacking → NOT a permission error; return early so caller treats as unsupported.
    if any(phrase in message for phrase in _PLAN_LACKING_PHRASES):
        return False, None
    # Classic token permission denial.
    if "Resource not accessible by integration" in message:
        return True, None
    # Fine-grained token scope missing.
    for err in exc_data.get("errors", []):
        if isinstance(err, dict) and err.get("code") == "missing":
            return True, err.get("field")
    return False, None


def _get_prefix() -> str:
    """Return GW_RESOURCE_PREFIX — the ownership marker for all gw-managed resources."""
    gw_prefix = os.environ.get("GW_RESOURCE_PREFIX", "")
    if not gw_prefix:
        raise EnvironmentError("GW_RESOURCE_PREFIX must be set and non-empty")
    return gw_prefix


def _is_managed(name: str, prefix: str) -> bool:
    return name.startswith(prefix)


class RulesetsManager:
    def __init__(self, gh_org):
        self._org = gh_org
        self._prefix = _get_prefix()

    def list_managed(self) -> list:
        """Return rulesets whose name starts with GW_RESOURCE_PREFIX.

        Returns empty list when the org plan does not support rulesets
        (GithubException with HTTP 403).  Other exceptions propagate.
        """
        try:
            _, data = self._org._requester.requestJsonAndCheck(
                "GET",
                f"/orgs/{self._org.login}/rulesets",
            )
        except Exception as exc:
            from github import GithubException  # local import to keep optional
            if isinstance(exc, GithubException) and exc.status == 403:
                denied, _perm = _is_permission_denied(exc.data)
                if denied:
                    raise  # permission error — caller must handle
                return []  # org plan does not support rulesets
            raise
        return [r for r in (data or []) if _is_managed(r.get("name", ""), self._prefix)]

    def apply(self, ruleset_cfg: dict) -> ResourceStatus:
        """Create or update a ruleset; return ResourceStatus.

        Returns 'skipped' when the org plan does not support rulesets (HTTP 403).
        """
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
            from github import GithubException  # local import to keep optional
            if not isinstance(exc, GithubException):
                # Non-GitHub exceptions (proxy errors, network failures, etc.)
                # always propagate — we have no status code to inspect.
                raise
            if exc.status == 403:
                denied, _perm = _is_permission_denied(exc.data)
                if denied:
                    raise  # permission error — propagate for caller to handle
                return ResourceStatus(name=name, status="skipped",
                                      error="org plan does not support rulesets")
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
