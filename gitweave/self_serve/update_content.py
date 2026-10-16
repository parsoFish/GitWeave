"""Self-serve update-content action for gitweave.

Apply a supported repository setting on behalf of a team caller if
their team's policy permits it.
"""
from __future__ import annotations

from gitweave.policy import PolicyDenied, check_permission


def self_serve_update_content(
    team: str,
    repo_name: str,
    setting: str,
    value,
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Apply *setting*=*value* to *repo_name*.

    Raises PolicyDenied if team lacks permission for this setting type.
    Returns {"applied": True}.
    Never opens a PR on the control repository.
    """
    check_permission(policy, team, "content-update")

    # Validate the specific setting type against the team's declared list.
    teams = policy.get("teams", [])
    team_policy = next((t for t in teams if t["slug"] == team), None)
    allowed_settings = team_policy.get("allowed_content_settings", []) if team_policy else []
    if setting not in allowed_settings:
        raise PolicyDenied(
            f"Setting '{setting}' is not in allowed_content_settings for team '{team}'."
        )

    repo = gh_org.get_repo(repo_name)

    if setting == "branch_protection":
        branch = value.get("branch", "main")
        kwargs = {k: v for k, v in value.items() if k != "branch"}
        repo.get_branch(branch).edit_protection(**kwargs)

    elif setting == "topics":
        repo.replace_topics(value)

    elif setting == "repo_variables":
        name = value["name"]
        val = value["value"]
        try:
            repo.update_variable(name, val)
        except Exception:
            repo.create_variable(name, val)

    elif setting == "environments":
        repo.create_environment(value)

    elif setting == "description":
        repo.edit(description=value)

    else:
        raise PolicyDenied(
            f"Setting '{setting}' is not a supported content setting."
        )

    return {"applied": True}
