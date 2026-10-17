"""gitweave.apply — apply declaration to live org; json_mode resets first."""
import json
from dataclasses import dataclass, field

from gitweave.config import load_config
from gitweave.managers.org import OrgSettingsManager, ResourceStatus
from gitweave.managers.teams import TeamsManager
from gitweave.managers.repos import ReposManager
from gitweave.managers.rulesets import RulesetsManager
from gitweave.managers.overlays import apply_overlays_for_repo
from gitweave.reset import reset


@dataclass
class ApplyResult:
    statuses: list[ResourceStatus] = field(default_factory=list)
    state: dict | None = None  # populated in json_mode

    @property
    def has_errors(self) -> bool:
        return any(s.status == "error" for s in self.statuses)

    def to_json(self) -> str:
        return json.dumps(
            {
                "statuses": [
                    {"name": s.name, "status": s.status, "error": s.error}
                    for s in self.statuses
                ],
                "state": self.state,
            },
            indent=2,
        )


def apply(gh_org, json_mode: bool = False) -> ApplyResult:
    """Apply declaration. json_mode=True → reset-before-apply, return JSON state."""
    if json_mode:
        reset(gh_org)

    cfg = load_config()
    result = ApplyResult()

    org_mgr = OrgSettingsManager(gh_org)
    result.statuses.append(org_mgr.apply(cfg["org_settings"]))

    teams_mgr = TeamsManager(gh_org)
    for team in cfg["teams"]:
        result.statuses.append(teams_mgr.apply(team))

    repos_mgr = ReposManager(gh_org)
    for repo in cfg["repos"]:
        result.statuses.append(repos_mgr.apply(repo))

    for repo_name in cfg.get("overlay_repos", []):
        apply_overlays_for_repo(repo_name, gh_org)

    rulesets_mgr = RulesetsManager(gh_org)
    for rs in cfg["rulesets"]:
        result.statuses.append(rulesets_mgr.apply(rs))

    if json_mode:
        result.state = _read_state(gh_org)

    return result


def _read_state(gh_org) -> dict:
    """Read current org state as a JSON-serialisable dict."""
    return {
        "org_settings": OrgSettingsManager(gh_org).current(),
        "teams": [{"name": t.name} for t in TeamsManager(gh_org).list_managed()],
        "repos": [{"name": r.name} for r in ReposManager(gh_org).list_managed()],
        "rulesets": RulesetsManager(gh_org).list_managed(),
    }
