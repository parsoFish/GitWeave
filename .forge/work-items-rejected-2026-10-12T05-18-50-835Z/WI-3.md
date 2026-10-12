---
work_item_id: WI-3
initiative_id: INIT-2026-10-11-i3a-green-apply-path
status: pending
depends_on:
  - WI-1
  - WI-2
acceptance_criteria:
  - given: "GW_RESOURCE_PREFIX is set and the live org is accessible via GW_APP_ID / GW_APP_INSTALLATION_ID / GW_APP_PRIVATE_KEY_PATH"
    when: "gw apply runs against the live throwaway org"
    then: "exits 0; only resources whose names start with GW_RESOURCE_PREFIX are touched; the org API is called with valid auth"
  - given: "GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX are both set (forge test-isolation mode)"
    when: "gw apply runs against the live throwaway org"
    then: "exits 0; only resources matching FORGE_RESOURCE_PREFIX are touched (narrowed scope); no resource outside FORGE_RESOURCE_PREFIX is mutated"
  - given: "the live apply acceptance test has run successfully"
    when: "gw reset runs with GW_RESOURCE_PREFIX set"
    then: "managed resources created by gw apply are removed; exits 0"
files_in_scope:
  - tests/acceptance/test_gw_apply_path.py
creates:
  - tests/acceptance/test_gw_apply_path.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "-p"
  - "no:cacheprovider"
  - "tests/acceptance/test_gw_apply_path.py::TestGwApplyPath::test_gw_apply_path_with_gw_resource_prefix"
domain: acceptance
---

# WI-3: Live acceptance — verify apply path with GW_RESOURCE_PREFIX

## Context

Satisfies AC3 from the initiative: the full GitWeave Apply workflow path (gw apply with GW_RESOURCE_PREFIX in env) must run green against the live throwaway org. This WI adds a focused acceptance test that exercises the complete apply→reset lifecycle with the new ownership marker.

Requires WI-1 (GW_RESOURCE_PREFIX scoping in plan.py/apply.py/reset.py) and WI-2 (workflow fixes) to be complete first.

## What to create

**`tests/acceptance/test_gw_apply_path.py` (new):**

Write `TestGwApplyPath` with:

- `test_gw_apply_path_with_gw_resource_prefix`:
  - Skip if required env vars missing (use `pytest.importorskip`-style skip guard matching `testProcess.acceptance.requiresEnv`: GW_ORG, GW_APP_ID, GW_APP_INSTALLATION_ID, GW_APP_PRIVATE_KEY_PATH)
  - Also requires GW_RESOURCE_PREFIX in env; skip if missing
  - Run `gw plan` (fixture mode) — assert exits 0
  - Run `gw apply` — assert exits 0
  - Verify no resource outside GW_RESOURCE_PREFIX was mutated (check the org state or rely on plan showing 0 unexpected changes)
  - Run `gw reset` — assert exits 0

- `test_forge_prefix_narrowing_live`:
  - Requires all above env vars PLUS FORGE_RESOURCE_PREFIX set
  - Skip if any missing
  - Run `gw plan` and `gw apply` with both prefixes set
  - Assert exits 0; assert scope is FORGE_RESOURCE_PREFIX resources only

## Constraint

Tests MUST be skippable when env vars are absent (CI without secrets passes; serve env with secrets passes). Follow the pattern in `tests/acceptance/test_gw_workflow.py` for skip guards.

---

**Brain themes consulted:**
- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/work-item-completion-by-domain.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
