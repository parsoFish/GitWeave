---
work_item_id: WI-1
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on: []
acceptance_criteria:
  - given: "config/policy.yaml is absent"
    when: "PolicyLoader.load() is called"
    then: "raises PolicyError with a message naming the missing file; exits non-zero when called via the CLI"
  - given: "config/policy.yaml exists but is not valid YAML"
    when: "PolicyLoader.load() is called"
    then: "raises PolicyError naming the parse problem; does not silently allow all requests"
  - given: "config/policy.yaml exists but fails jsonschema validation (e.g. missing required field)"
    when: "PolicyLoader.load() is called"
    then: "raises PolicyError with the schema validation message"
  - given: "a team slug that does not appear in config/policy.yaml"
    when: "policy.check_permission(team='unknown-team', request_type='new-repo') is called"
    then: "raises PolicyDenied naming the team and stating it has no declared permissions"
  - given: "a team that has 'new-repo' in its allowed_request_types and the repo name matches allowed_patterns"
    when: "policy.check_permission(team='platform', request_type='new-repo', repo_name='forge-foo') is called"
    then: "returns True without raising"
  - given: "a team that does NOT have the requested request_type in its allowed_request_types"
    when: "policy.check_permission is called for that type"
    then: "raises PolicyDenied citing the specific rule name (e.g. 'new-repo not in platform.allowed_request_types')"
  - given: "a repo name that does not match the team's allowed_repo_patterns"
    when: "policy.check_permission(team, 'new-repo', repo_name='not-allowed') is called"
    then: "raises PolicyDenied naming the pattern rule"
files_in_scope:
  - gitweave/policy.py
  - config/policy.yaml
  - tests/test_policy.py
  - gitweave/self_serve/__init__.py
creates:
  - gitweave/policy.py
  - config/policy.yaml
  - tests/test_policy.py
  - gitweave/self_serve/__init__.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_policy.py::TestPolicyLoader::test_absent_policy_exits_nonzero"
  - "-p"
  - "no:cacheprovider"
domain: "policy"
---

# WI-1: Policy engine + self-serve package scaffold

Target: `gitweave/policy.py` — a `PolicyLoader` class that loads/validates `config/policy.yaml` and a `check_permission` function used by every self-serve subcommand. Also creates the `gitweave/self_serve/` package directory so WI-3 through WI-6 can run in parallel.

## policy.yaml schema

```yaml
# config/policy.yaml
teams:
  - slug: platform-team
    allowed_request_types:
      - new-repo
      - content-update
      - team-membership
      - policy-exception
    allowed_repo_patterns:
      - "forge-*"
    allowed_content_settings:
      - branch_protection
      - repo_variables
      - environments
      - topics
      - description
```

`config/policy.yaml` must include a realistic example entry for the throwaway org (`dave-parso`) with a `forge-`-prefixed naming pattern so live acceptance tests can use it.

## PolicyLoader contract

```python
class PolicyError(Exception): ...
class PolicyDenied(PolicyError): ...

class PolicyLoader:
    def load(self) -> dict:
        """Loads and validates config/policy.yaml. Raises PolicyError on any problem."""

def check_permission(policy: dict, team: str, request_type: str, **kwargs) -> None:
    """Raises PolicyDenied (naming the specific rule) if the request is not allowed.
    Never raises on a permitted request. Never silently permits an absent team."""
```

## Self-serve package scaffold

`gitweave/self_serve/__init__.py` — empty; just creates the package so WI-3–6 can import from it.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
