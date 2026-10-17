"""Self-serve new-repo action for gitweave.

Business logic: create a GitHub repository on behalf of a caller if
their team's policy permits it.
"""
from __future__ import annotations

from github import GithubException

from gitweave.policy import PolicyDenied, check_permission


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
    # Delegates all permission checks (team existence, request type,
    # repo-name pattern) to the centralised check_permission gate.
    check_permission(policy, team, "new-repo", repo_name=name)

    # Create the repo (idempotent: treat 422 "already exists" as success)
    try:
        gh_org.create_repo(name)
    except GithubException as exc:
        if exc.status == 422 and "already exists" in str(exc.data).lower():
            return {"created": False, "reason": "already_exists"}
        raise

    return {"created": True}
