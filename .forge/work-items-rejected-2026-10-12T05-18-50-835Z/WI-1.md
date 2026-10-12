---
work_item_id: WI-1
initiative_id: INIT-2026-10-11-i3a-green-apply-path
status: pending
depends_on: []
acceptance_criteria:
  - given: "GW_RESOURCE_PREFIX is set in the environment and FORGE_RESOURCE_PREFIX is unset"
    when: "plan() is called in fixture mode"
    then: "resources are scoped to names starting with GW_RESOURCE_PREFIX; plan() completes without EnvironmentError and returns a PlanResult"
  - given: "both GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX are set, where FORGE_RESOURCE_PREFIX starts with GW_RESOURCE_PREFIX"
    when: "plan() is called in fixture mode"
    then: "only resources matching FORGE_RESOURCE_PREFIX (the narrower prefix) are included; a resource matching GW_RESOURCE_PREFIX but not FORGE_RESOURCE_PREFIX is absent from the result"
  - given: "GW_RESOURCE_PREFIX is unset (empty string) and FORGE_RESOURCE_PREFIX is also unset"
    when: "plan() is called in fixture mode"
    then: "plan() includes all declared resources (prefix is empty string, so all names start with it)"
files_in_scope:
  - gitweave/plan.py
  - gitweave/apply.py
  - gitweave/reset.py
  - tests/test_plan.py
  - tests/test_ownership_marker.py
creates:
  - tests/test_ownership_marker.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "-p"
  - "no:cacheprovider"
  - "tests/test_ownership_marker.py::TestOwnershipMarker::test_plan_scopes_by_gw_resource_prefix"
domain: api
---

# WI-1: GW_RESOURCE_PREFIX ownership marker

## Context

`plan.py:70` reads `FORGE_RESOURCE_PREFIX` — a forge test-isolation variable with no place in GitWeave's production path. This WI replaces it with `GW_RESOURCE_PREFIX` as GitWeave's own ownership marker, and treats `FORGE_RESOURCE_PREFIX` as an optional narrowing filter (used in forge test runs to scope the throwaway org prefix further).

## What to change

**`gitweave/plan.py`:**
Replace:
```python
prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
```
With:
```python
gw_prefix = os.environ.get("GW_RESOURCE_PREFIX", "")
forge_prefix = os.environ.get("FORGE_RESOURCE_PREFIX", "")
# FORGE_RESOURCE_PREFIX narrows scope when set; must start with gw_prefix to be valid.
# If forge_prefix is non-empty and starts with gw_prefix, use it as the effective prefix.
# Otherwise fall back to gw_prefix (or warn if forge_prefix doesn't extend gw_prefix).
if forge_prefix:
    prefix = forge_prefix  # narrows — forge_prefix must be ⊆ gw_prefix space
else:
    prefix = gw_prefix
```

Pass `prefix` through to `_live_snapshot` and `_diff` exactly as today.

**`gitweave/apply.py`:** Apply the same two-variable pattern — read `GW_RESOURCE_PREFIX` as primary, `FORGE_RESOURCE_PREFIX` as optional narrowing.

**`gitweave/reset.py`:** Same pattern. Reset scope must match plan/apply scope from day one so reset only touches resources the marker owns.

**`tests/test_plan.py`:** Update any assertions that reference `FORGE_RESOURCE_PREFIX` as the primary ownership env var to use `GW_RESOURCE_PREFIX` instead.

**`tests/test_ownership_marker.py` (new):** Write `TestOwnershipMarker` with:
- `test_plan_scopes_by_gw_resource_prefix` — fixture-mode plan with only `GW_RESOURCE_PREFIX` set, verifies resource filtering
- `test_forge_prefix_narrows_scope` — both vars set; verifies resources matching gw_prefix but not forge_prefix are excluded
- Use `monkeypatch.setenv`/`monkeypatch.delenv` to control env vars; pass `tests/fixtures/org-empty.json` as fixture

## Constraint

Do NOT remove `FORGE_RESOURCE_PREFIX` support entirely — forge acceptance tests rely on it for test isolation. The semantics: `GW_RESOURCE_PREFIX` gates ownership; `FORGE_RESOURCE_PREFIX` (when set) narrows further.

---

**Brain themes consulted:**
- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/work-item-completion-by-domain.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
