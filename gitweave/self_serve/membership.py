"""Self-serve team membership actions for gitweave.

Business logic: add or remove a team member on behalf of a caller if
their team's policy permits it and the caller is an active team member.
"""
from __future__ import annotations

from github import GithubException

from gitweave.auth import get_github_client
from gitweave.policy import PolicyDenied


def _require_team_policy(team: str, policy: dict) -> dict:
    """Return the team's policy entry or raise PolicyDenied."""
    teams = policy.get("teams", [])
    team_policy = next((t for t in teams if t["slug"] == team), None)
    if team_policy is None:
        raise PolicyDenied(
            f"Team '{team}' has no declared permissions in policy; request denied."
        )
    return team_policy


def _require_permission(team: str, team_policy: dict, permission: str) -> None:
    """Raise PolicyDenied if *permission* is not in team's allowed_request_types."""
    if permission not in team_policy.get("allowed_request_types", []):
        raise PolicyDenied(
            f"Team '{team}' is not permitted to manage team membership."
        )


def _require_caller_is_member(gh_team, caller_login: str, team: str) -> None:
    """Verify caller is an active member of the team via the App token.

    Raises PolicyDenied if the membership is absent, pending, or returns a 404.
    """
    try:
        membership = gh_team.get_team_membership(caller_login)
    except GithubException as exc:
        if exc.status == 404:
            raise PolicyDenied(
                f"Caller '{caller_login}' is not a member of team '{team}'; request denied."
            ) from exc
        raise

    if membership is None or membership.state != "active":
        raise PolicyDenied(
            f"Caller '{caller_login}' is not an active member of team '{team}'; request denied."
        )


def self_serve_add_member(
    team: str,
    member_login: str,
    gh_org,
    policy: dict,
    caller_login: str,
    gh=None,
) -> dict:
    """Add *member_login* to *team*.

    Verifies caller is a current active member of *team* (using App token via gh_org).
    Raises PolicyDenied if team not in policy, permission not allowed, or caller not a member.
    Returns {"applied": True}.
    Never opens a PR on the control repository.

    *gh* is the root Github client used to resolve *member_login* to a NamedUser.
    When omitted the App-token client is obtained via ``get_github_client()``.
    """
    team_policy = _require_team_policy(team, policy)
    _require_permission(team, team_policy, "team-membership")

    gh_team = gh_org.get_team_by_slug(team)
    _require_caller_is_member(gh_team, caller_login, team)

    _gh = gh if gh is not None else get_github_client()
    member_user = _gh.get_user(member_login)
    gh_team.add_membership(member_user)
    return {"applied": True}


def self_serve_remove_member(
    team: str,
    member_login: str,
    gh_org,
    policy: dict,
    caller_login: str,
    gh=None,
) -> dict:
    """Remove *member_login* from *team*. Same auth/policy checks as add.

    Raises PolicyDenied if team not in policy, permission not allowed, or caller not a member.
    Returns {"applied": True}.
    Never opens a PR on the control repository.

    *gh* is the root Github client used to resolve *member_login* to a NamedUser.
    When omitted the App-token client is obtained via ``get_github_client()``.
    """
    team_policy = _require_team_policy(team, policy)
    _require_permission(team, team_policy, "team-membership")

    gh_team = gh_org.get_team_by_slug(team)
    _require_caller_is_member(gh_team, caller_login, team)

    _gh = gh if gh is not None else get_github_client()
    member_user = _gh.get_user(member_login)
    gh_team.remove_membership(member_user)
    return {"applied": True}
