"""Self-service overlay request — team-driven module application."""
from __future__ import annotations

from gitweave.managers.overlays import apply_module_to_repo, ModuleSpec
from gitweave.policy import PolicyDenied, PolicyError  # noqa: F401 (re-exported)


class OverlayRequestDenied(PolicyDenied):
    """Raised when a module request is denied by policy."""


def self_serve_overlay_request(
    team: str,
    repo: str,
    module_name: str,
    gh_org,
    policy,
    caller_login: str,
    transport=None,
) -> dict:
    """Check policy, then apply module to repo with no PR.

    Args:
        team: Team slug making the request.
        repo: Repository name (without org prefix).
        module_name: Module name to apply.
        gh_org: GitHub org object (must have a ``login`` attribute).
        policy: PolicyLoader instance or raw policy dict (``allowed_modules_for_team``
            method or ``teams`` list).
        caller_login: GitHub login of the requesting user.
        transport: RecordingTransport (or compatible).  If *None* a no-op
            recording transport is created so callers can always call
            ``transport.assert_no_pr_opens()`` after the call.

    Returns:
        dict with keys ``action``, ``repo``, ``module``.

    Raises:
        OverlayRequestDenied: if module not in team's allowed_modules.
        PolicyError: if policy.yaml is absent or invalid.
    """
    # Support both a PolicyLoader instance and a raw policy dict (the CLI
    # passes the result of PolicyLoader().load(), i.e. a dict).
    if hasattr(policy, "allowed_modules_for_team"):
        allowed = policy.allowed_modules_for_team(team)
    else:
        teams = policy.get("teams", [])
        team_cfg = next((t for t in teams if t.get("slug") == team), None)
        allowed = list(team_cfg.get("allowed_modules", [])) if team_cfg else []
    if module_name not in allowed:
        raise OverlayRequestDenied(
            f"policy-module-not-allowed: module '{module_name}' is not in "
            f"team '{team}' allowed_modules (rule: allowed_modules)"
        )

    if transport is None:
        from gitweave.transport import RecordingTransport
        transport = RecordingTransport(handler=lambda m, u, **kw: {})

    org_login = getattr(gh_org, "login", "org")
    repo_full_name = f"{org_login}/{repo}"
    spec = ModuleSpec(name=module_name, version="latest", inputs={})
    result = apply_module_to_repo(repo_full_name, spec, transport)
    return {"action": result.action, "repo": repo, "module": module_name}
