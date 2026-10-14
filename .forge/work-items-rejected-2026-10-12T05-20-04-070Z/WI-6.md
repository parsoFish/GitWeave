---
work_item_id: WI-6
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-1
  - WI-2
acceptance_criteria:
  - given: "team policy allows 'policy-exception' for the repo and exception_name is in allowed_exceptions"
    when: "self_serve_add_exception(team, repo_name, exception_name, reason, gh_org, policy, caller_login) is called"
    then: "creates the org-level custom property definition (idempotent) and sets it on the repo; returns success"
  - given: "the org-level custom property definition already exists"
    when: "self_serve_add_exception is called again"
    then: "does not raise; sets the property on the repo (idempotent on the definition creation step)"
  - given: "a repo with one or more exception custom properties set"
    when: "self_serve_list_exceptions(repo_name, gh_org) is called"
    then: "returns a list of dicts with exception_name and value read back via the GitHub API"
  - given: "team not in policy or exception type not allowed"
    when: "self_serve_add_exception is called"
    then: "raises PolicyDenied naming the specific rule"
files_in_scope:
  - gitweave/self_serve/exceptions.py
  - tests/test_self_serve_exceptions.py
creates:
  - gitweave/self_serve/exceptions.py
  - tests/test_self_serve_exceptions.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_self_serve_exceptions.py::TestPolicyExceptions::test_exception_recorded_as_custom_property"
  - "-p"
  - "no:cacheprovider"
domain: "self-serve"
---

# WI-6: Policy exception recording via GitHub custom properties

Target: `gitweave/self_serve/exceptions.py`.

## GitHub custom property API

- **Org-level definition**: `PATCH /orgs/{org}/properties/schema` — creates or updates a property definition (idempotent; handle "property already exists" as success).
- **Repo-level set**: `PATCH /repos/{org}/{repo}/properties/values`
- **Read-back**: `GET /repos/{org}/{repo}/properties/values`

PyGithub may not expose these endpoints in the installed version — use `gh_org._requester.requestJsonAndCheck` for raw REST calls if needed.

## Function contract

```python
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

def self_serve_list_exceptions(repo_name: str, gh_org) -> list[dict]:
    """Return exceptions recorded on *repo_name* via the GitHub API."""
```

## policy.yaml extension needed

Add `allowed_exceptions` list to each team entry in `config/policy.yaml` (the ralph loop should also update the example policy created in WI-1 if the field was not included there).

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
