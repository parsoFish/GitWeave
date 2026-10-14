"""Self-serve new-repo action for gitweave.

Business logic: create a GitHub repository on behalf of a caller if
their team's policy permits it.
"""
from __future__ import annotations

from github import GithubException

from gitweave.policy import PolicyDenied


def self_serve_new_repo(
    team: str,
    name: str,
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Create *name* under *gh_org* if permitted by *policy* for *team*.

    Returns {"created": True} or {"created": False, "reason": "already_exists"}.
    Raises PolicyDenied if the request violates policy.
    Never opens a PR or branch on the control repository.
    """
    # Find team entry in policy
    teams = policy.get("teams", [])
    team_policy = next((t for t in teams if t["slug"] == team), None)

    if team_policy is None:
        raise PolicyDenied(
            f"Team '{team}' has no declared permissions in policy; request denied."
        )

    # Check action is allowed
    if "new-repo" not in team_policy.get("allowed_request_types", []):
        raise PolicyDenied(
            f"Team '{team}' is not permitted to create new repositories."
        )

    # Validate name against allowed patterns
    import fnmatch

    patterns = team_policy.get("allowed_repo_patterns", [])
    if patterns:
        matched = any(fnmatch.fnmatch(name, p) for p in patterns)
        if not matched:
            raise PolicyDenied(
                f"Repo name '{name}' does not match any allowed_repo_patterns "
                f"for team '{team}': {patterns}"
            )

    # Create the repo (idempotent: treat 422 "already exists" as success)
    try:
        gh_org.create_repo(name)
    except GithubException as exc:
        if exc.status == 422 and "already exists" in str(exc.data).lower():
            return {"created": False, "reason": "already_exists"}
        raise

    return {"created": True}
