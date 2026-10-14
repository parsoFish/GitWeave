---
work_item_id: WI-5
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-1
  - WI-2
acceptance_criteria:
  - given: "team policy allows 'team-membership' and caller_login is a member of the team per the live org (mocked)"
    when: "self_serve_add_member(team, member_login, gh_org, policy, caller_login) is called"
    then: "calls the team's add_to_members API method and returns success"
  - given: "caller is not a member of the team (mocked membership check returns False)"
    when: "self_serve_add_member is called"
    then: "raises PolicyDenied stating caller is not a member of the team"
  - given: "team not in policy.yaml"
    when: "self_serve_add_member is called"
    then: "raises PolicyDenied naming the team and stating no declared permissions"
  - given: "team policy allows 'team-membership' and caller is a team member"
    when: "self_serve_remove_member(team, member_login, gh_org, policy, caller_login) is called"
    then: "calls the team's remove_from_members API method and returns success"
files_in_scope:
  - gitweave/self_serve/membership.py
  - tests/test_self_serve_membership.py
creates:
  - gitweave/self_serve/membership.py
  - tests/test_self_serve_membership.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_self_serve_membership.py::TestSelfServeMembership::test_policy_violation_exits_nonzero"
  - "-p"
  - "no:cacheprovider"
domain: "self-serve"
---

# WI-5: gw self-serve add-member / remove-member

Target: `gitweave/self_serve/membership.py`.

## Caller verification

The caller is verified as a current team member using the App token (not the caller token): `GET /orgs/{org}/teams/{slug}/memberships/{caller_login}`. If state is not `"active"`, the request is denied.

## Function contract

```python
def self_serve_add_member(
    team: str,
    member_login: str,
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Add *member_login* to *team*.

    Verifies caller is a current member of *team* (using App token via gh_org).
    Raises PolicyDenied if team not in policy, permission not allowed, or caller not a member.
    Returns {"applied": True}.
    Never opens a PR on the control repository.
    """

def self_serve_remove_member(
    team: str,
    member_login: str,
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Remove *member_login* from *team*. Same auth/policy checks as add."""
```

## Tests (unit — mock gh_org and team object)

`test_policy_violation_exits_nonzero` — caller not in team → PolicyDenied (collection fails until file is created).

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
