---
work_item_id: WI-8
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-3
  - WI-5
  - WI-6
acceptance_criteria:
  - given: "a self-serve-managed repo declared in policy.yaml that does not yet exist in the snapshot"
    when: "_diff() processes the snapshot"
    then: "PlanResult includes a PlanItem(resource_type='self_serve_repo', action='create')"
  - given: "a self-serve-managed repo that exists in both declared policy and the snapshot"
    when: "_diff() processes the snapshot"
    then: "PlanResult includes a PlanItem(resource_type='self_serve_repo', action='unchanged')"
  - given: "a self-serve-managed repo present in the snapshot but removed from policy.yaml"
    when: "_diff() processes the snapshot"
    then: "PlanResult includes a PlanItem(resource_type='self_serve_repo', action='delete')"
  - given: "a policy exception (custom property) set on a repo that is no longer in policy.yaml exceptions list"
    when: "_diff() processes the snapshot"
    then: "PlanResult includes a PlanItem(resource_type='policy_exception', action='delete')"
  - given: "a team membership declared in policy.yaml team membership list but not present in the snapshot"
    when: "_diff() processes the snapshot"
    then: "PlanResult includes a PlanItem(resource_type='team_membership', action='create')"
files_in_scope:
  - gitweave/plan.py
  - tests/test_plan_self_serve.py
creates:
  - tests/test_plan_self_serve.py
verification_artifact: gitweave/plan.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_plan_self_serve.py::TestPlanSelfServe::test_self_serve_repo_delete_action"
  - "-p"
  - "no:cacheprovider"
domain: "plan"
---

# WI-8: Plan engine — three state branches for self-serve resource types

Target: extend `gitweave/plan.py` to diff self-serve resource types (self_serve_repo, policy_exception, team_membership) with all three action branches: create / unchanged / delete.

## Plan engine extension

The plan engine compares:
- **self_serve_repo**: declared repos in `policy.yaml` (all teams' allowed repos × naming patterns that are explicitly created, tracked as a `self_serve_repos` section in policy.yaml) vs. repos in the snapshot prefixed with the forge prefix.
- **policy_exception**: declared exceptions in `policy.yaml` vs. custom properties read from the snapshot.
- **team_membership**: declared memberships in `policy.yaml` vs. live memberships in the snapshot.

Extend `_live_snapshot` to also capture these from the live org (populated by `self_serve_add_exception`, etc.) and extend `_diff` to process the three new resource types.

All three types follow the same set arithmetic pattern already used for teams/repos/rulesets in `_diff`: declared_names − snap_names = create, snap_names − declared_names = delete, intersection = unchanged.

The fixture format must be extended to include `self_serve_repos`, `policy_exceptions`, and `team_memberships` arrays (defaulting to `[]` when absent so existing fixtures continue to work).

## Three-state branch mandate (I3b plan-engine requirement)

Per the initiative body: prior I2 cycle lost 8 gate runs to a missing delete branch. All three branches must be exercised by tests using fixture-mode plan calls (no network).

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
- `brain/cycles/themes/work-item-completion-by-domain.md`
