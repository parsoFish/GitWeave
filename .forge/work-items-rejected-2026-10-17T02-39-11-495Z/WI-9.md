---
work_item_id: WI-9
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on:
  - WI-7
  - WI-5
domain: self_serve
acceptance_criteria:
  - given: "config/policy.yaml declares python_service allowed for team-a, and team-a owns the target repo"
    when: "gw overlay request --team team-a --repo target-repo --module python_service runs via RecordingTransport"
    then: "the module is applied with no pull request (transport.assert_no_pr_opens() passes); exit 0"
  - given: "config/policy.yaml declares terraform_module NOT in team-a's allowed_modules"
    when: "gw overlay request --team team-a --repo target-repo --module terraform_module runs"
    then: "exits non-zero; prints the policy rule name; zero write-call records in the transport log after the refusal"
  - given: "config/policy.yaml is absent"
    when: "gw overlay request runs"
    then: "exits non-zero with a named policy rule error (not FileNotFoundError); zero write calls"
  - given: "the CLI parser"
    when: "gw overlay request --help is called"
    then: "exit 0; the overlay request subcommand is registered with --team, --repo, --module arguments"
files_in_scope:
  - gitweave/self_serve/overlay_request.py
  - gitweave/cli.py
  - gitweave/policy.py
  - tests/test_overlay_request.py
creates:
  - gitweave/self_serve/overlay_request.py
  - tests/test_overlay_request.py
estimated_iterations: 4
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_overlay_request.py::TestOverlayRequest::test_allowed_module_applied_no_pr"
  - "-p"
  - "no:cacheprovider"
---

# WI-9: gw overlay request — self-service + policy enforcement

Target: `gitweave/self_serve/overlay_request.py` (new), `gitweave/cli.py` (add overlay request), `tests/test_overlay_request.py` (new). Extends `gitweave/policy.py` as needed for the `allowed_modules_for_team` method.

## gitweave/self_serve/overlay_request.py

```python
"""Self-service overlay request — team-driven module application."""

from gitweave.managers.overlays import apply_module_to_repo, ModuleSpec
from gitweave.policy import PolicyLoader, PolicyDenied, PolicyError


class OverlayRequestDenied(PolicyDenied):
    """Raised when a module request is denied by policy."""


def self_serve_overlay_request(
    team: str,
    repo: str,
    module_name: str,
    gh_org,
    policy,
    caller_login: str,
) -> dict:
    """Check policy, then apply module to repo with no PR.
    
    Raises:
        OverlayRequestDenied: if module not in team's allowed_modules.
        PolicyError: if policy.yaml is absent or invalid.
    """
    allowed = policy.allowed_modules_for_team(team)
    if module_name not in allowed:
        raise OverlayRequestDenied(
            f"policy-module-not-allowed: module '{module_name}' is not in "
            f"team '{team}' allowed_modules (rule: allowed_modules)"
        )

    gh_repo = gh_org.get_repo(repo)
    # Load declared inputs from config/repos/<repo>.yaml if present, else empty
    inputs = {}  # default; caller may override
    spec = ModuleSpec(name=module_name, version="latest", inputs=inputs)
    result = apply_module_to_repo(gh_repo, spec)
    return {"action": result.action, "repo": repo, "module": module_name}
```

Note: The `version` for a self-service request should come from the module's own `copier.yaml` `_metadata.version` field — load it at request time. Update the implementation accordingly.

## CLI wiring: gitweave/cli.py

Add `request` subcommand to the existing `overlay` subparser group (WI-7 added `status`; WI-9 adds `request`):

```python
p_or = ov_sub.add_parser("request", help="Request a module for a team repo")
p_or.add_argument("--team", required=True, metavar="SLUG")
p_or.add_argument("--repo", required=True, metavar="REPO")
p_or.add_argument("--module", required=True, metavar="NAME")
p_or.set_defaults(func=cmd_overlay_request)
```

```python
def cmd_overlay_request(args):
    from gitweave.self_serve.overlay_request import self_serve_overlay_request, OverlayRequestDenied
    try:
        gh_org, policy, caller_login = _self_serve_auth()
        result = self_serve_overlay_request(
            args.team, args.repo, args.module, gh_org, policy, caller_login
        )
        import json
        print(json.dumps(result))
        sys.exit(0)
    except CallerTokenRequiredError as e:
        print(f"caller-token-required: {e}", file=sys.stderr)
        sys.exit(1)
    except (PolicyError, OverlayRequestDenied) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
```

## tests/test_overlay_request.py

Use `RecordingTransport` for transport-level assertions. Tests must NOT inherit any GW_* autouse fixture.

Class `TestOverlayRequest`:
- `test_allowed_module_applied_no_pr` — patches policy to allow `python_service` for team-a; patches overlay apply; asserts `transport.assert_no_pr_opens()` passes; exit 0
- `test_denied_module_exits_nonzero` — patches policy with empty allowed_modules; asserts exit 1; policy rule name in stderr; zero write calls
- `test_policy_absent_exits_nonzero` — patches `PolicyLoader.load()` to raise `PolicyError`; asserts exit 1; zero write calls after refusal
- `test_request_help_exits_zero` — `gw overlay request --help` exits 0

## autouse fixture caution

Per constraint `2026-10-13-autouse-fixture-env-masking`: if any GW_* env vars are set by an autouse conftest, these tests must either explicitly unset them or be structured to not inherit the fixture. Use `@pytest.mark.usefixtures` overrides or isolate in a separate conftest scope.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
