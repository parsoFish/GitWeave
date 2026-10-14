---
work_item_id: WI-3
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-1
  - WI-2
acceptance_criteria:
  - given: "policy allows new-repo for the team and name matches the allowed pattern"
    when: "self_serve_new_repo(team, name, gh_org, policy, caller_login) is called"
    then: "calls gh_org.create_repo with the correct name and returns a success result"
  - given: "same command called when the repo already exists"
    when: "self_serve_new_repo is called a second time"
    then: "returns success without raising (idempotent — exits 0)"
  - given: "repo name does not match the team's allowed_repo_patterns in policy"
    when: "self_serve_new_repo is called"
    then: "raises PolicyDenied naming the pattern rule; no API call is made"
  - given: "team not present in policy.yaml"
    when: "self_serve_new_repo is called"
    then: "raises PolicyDenied naming the team and stating no declared permissions"
files_in_scope:
  - gitweave/self_serve/new_repo.py
  - tests/test_self_serve_new_repo.py
creates:
  - gitweave/self_serve/new_repo.py
  - tests/test_self_serve_new_repo.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_self_serve_new_repo.py::TestSelfServeNewRepo::test_policy_violation_exits_nonzero"
  - "-p"
  - "no:cacheprovider"
domain: "self-serve"
---

# WI-3: gw self-serve new-repo

Target: `gitweave/self_serve/new_repo.py` — the business logic for creating a repository via the GitHub App on behalf of a caller.

## Function contract

```python
from gitweave.policy import PolicyDenied

def self_serve_new_repo(
    team: str,
    name: str,
    gh_org,          # PyGithub Organization object
    policy: dict,    # loaded policy dict from PolicyLoader
    caller_login: str,
) -> dict:
    """Create *name* under *gh_org* if permitted by *policy* for *team*.

    Returns {"created": True} or {"created": False, "reason": "already_exists"}.
    Raises PolicyDenied if the request violates policy.
    Never opens a PR or branch on the control repository.
    """
```

## Idempotency

Catch `GithubException` with status 422 / "already exists" message → return `{"created": False, "reason": "already_exists"}` (caller treats this as exit 0).

## Tests (unit — use MagicMock for gh_org)

`test_policy_violation_exits_nonzero` must be the collection-failing node (file doesn't exist yet → pytest exits non-zero at collection = discriminating gate).

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
