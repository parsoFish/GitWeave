"""gitweave.reset — delete all prefixed resources and restore org defaults."""
import os
from dataclasses import dataclass, field

from gitweave.managers.org import OrgSettingsManager, ORG_DEFAULTS, ResourceStatus
from gitweave.managers.teams import TeamsManager
from gitweave.managers.repos import ReposManager
from gitweave.managers.rulesets import RulesetsManager


@dataclass
class ResetResult:
    statuses: list[ResourceStatus] = field(default_factory=list)
    nothing_changed: bool = False


def reset(gh_org) -> ResetResult:
    """Delete all prefixed resources + restore org settings to safe defaults.

    404 on any individual resource → success (idempotent).
    Sets nothing_changed=True when org was already clean and at defaults.
    """
    gw_prefix = os.environ.get("GW_RESOURCE_PREFIX", "")
    forge_prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
    # FORGE_RESOURCE_PREFIX narrows scope to the initiative when set;
    # takes full priority over GW_RESOURCE_PREFIX (they are independent namespaces).
    # When neither is set, reset has no safe prefix to operate on.
    if not gw_prefix and not forge_prefix:
        raise EnvironmentError("GW_RESOURCE_PREFIX must be set and non-empty for reset")

    result = ResetResult()
    changed = False

    teams_mgr = TeamsManager(gh_org)
    for team in teams_mgr.list_managed():
        changed = True
        result.statuses.append(teams_mgr.delete(team.name))

    repos_mgr = ReposManager(gh_org)
    for repo in repos_mgr.list_managed():
        changed = True
        result.statuses.append(repos_mgr.delete(repo.name))

    rulesets_mgr = RulesetsManager(gh_org)
    for rs in rulesets_mgr.list_managed():
        changed = True
        result.statuses.append(rulesets_mgr.delete(rs["name"]))

    # Restore org settings to GitHub safe defaults (only when they differ)
    org_mgr = OrgSettingsManager(gh_org)
    if org_mgr.current() != ORG_DEFAULTS:
        changed = True
        result.statuses.append(org_mgr.reset())

    result.nothing_changed = not changed
    return result
