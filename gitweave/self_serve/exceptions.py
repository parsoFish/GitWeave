"""Self-serve policy-exception recording via GitHub custom properties.

Uses org-level custom property definitions to record exceptions on repos.
"""
from __future__ import annotations

from gitweave.policy import PolicyDenied, check_permission

EXCEPTION_PROPERTY_NAME = "gw-policy-exception"


def self_serve_add_exception(
    team: str,
    repo_name: str,
    exception_name: str,
    reason: str,
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Record a policy exception as a custom property on *repo_name*.

    Creates org-level property definition on first use (idempotent).
    Raises PolicyDenied if not allowed.
    Returns {"applied": True, "property": EXCEPTION_PROPERTY_NAME}.
    Never opens a PR on the control repository.
    """
    check_permission(policy, team, "policy-exception")

    # Validate the specific exception type against the team's declared list.
    teams = policy.get("teams", [])
    team_policy = next((t for t in teams if t["slug"] == team), None)
    allowed_exceptions = team_policy.get("allowed_exceptions", []) if team_policy else []
    if not allowed_exceptions:
        raise PolicyDenied(
            f"allowed_exceptions for team '{team}' is empty or absent; "
            f"exception requests are denied by default (fail-closed): {allowed_exceptions}"
        )
    if exception_name not in allowed_exceptions:
        raise PolicyDenied(
            f"Exception type '{exception_name}' is not in allowed_exceptions for team '{team}': {allowed_exceptions}"
        )

    org_login = gh_org.login

    # Create or update org-level property definition (idempotent)
    _ensure_property_definition(gh_org, org_login, EXCEPTION_PROPERTY_NAME)

    # Set the property on the repo
    _set_repo_property(gh_org, org_login, repo_name, EXCEPTION_PROPERTY_NAME, exception_name)

    return {"applied": True, "property": EXCEPTION_PROPERTY_NAME}


def self_serve_list_exceptions(repo_name: str, gh_org) -> list[dict]:
    """Return exceptions recorded on *repo_name* via the GitHub API."""
    org_login = gh_org.login
    _, data = gh_org._requester.requestJsonAndCheck(
        "GET",
        f"/repos/{org_login}/{repo_name}/properties/values",
    )
    results = []
    for item in data or []:
        prop_name = item.get("property_name", "")
        if prop_name.startswith("gw-policy-exception"):
            results.append({
                "exception_name": item.get("value"),
                "value": item.get("value"),
            })
    return results


def _ensure_property_definition(gh_org, org_login: str, property_name: str) -> None:
    """Create org-level custom property definition; ignore 422 (already exists)."""
    try:
        gh_org._requester.requestJsonAndCheck(
            "PATCH",
            f"/orgs/{org_login}/properties/schema",
            input={
                "properties": [
                    {
                        "property_name": property_name,
                        "value_type": "string",
                        "required": False,
                        "description": "Policy exception recorded by gitweave self-serve",
                    }
                ]
            },
        )
    except Exception as exc:
        # 422 means property already exists — treat as success
        msg = str(exc).lower()
        if "422" in msg or "already exist" in msg or "unprocessable" in msg:
            return
        raise


def _set_repo_property(
    gh_org, org_login: str, repo_name: str, property_name: str, value: str
) -> None:
    """Set a custom property value on a repo."""
    gh_org._requester.requestJsonAndCheck(
        "PATCH",
        f"/repos/{org_login}/{repo_name}/properties/values",
        input={
            "properties": [
                {"property_name": property_name, "value": value}
            ]
        },
    )
