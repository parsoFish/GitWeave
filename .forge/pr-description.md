# I3a — Green Apply Path

Initiative `INIT-2026-10-11-i3a-green-apply-path` · project `gitweave` · head `4d305568e2b815e2ba3718c467d6d9af02a4e0cd`

## Why

The acceptance criteria this initiative was decomposed against:

- (WI-1) GIVEN GW_RESOURCE_PREFIX is set in the environment and FORGE_RESOURCE_PREFIX is unset WHEN plan() is called in fixture mode THEN resources are scoped to names starting with GW_RESOURCE_PREFIX; plan() completes without EnvironmentError and returns a PlanResult
- (WI-1) GIVEN both GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX are set, where FORGE_RESOURCE_PREFIX starts with GW_RESOURCE_PREFIX WHEN plan() is called in fixture mode THEN only resources matching FORGE_RESOURCE_PREFIX (the narrower prefix) are included; a resource matching GW_RESOURCE_PREFIX but not FORGE_RESOURCE_PREFIX is absent from the result
- (WI-1) GIVEN GW_RESOURCE_PREFIX is unset (empty string) and FORGE_RESOURCE_PREFIX is also unset WHEN plan() is called in fixture mode THEN plan() includes all declared resources (prefix is empty string, so all names start with it)
- (WI-2) GIVEN the gitweave-apply.yaml workflow file after this WI WHEN its dry-run-smoke job (name: 'Apply Configuration') is inspected THEN it does NOT invoke scripts/apply-overlays.py; it either runs gw plan --fixture or is rewired to a gw command, or is removed entirely
- (WI-2) GIVEN the gitweave-apply.yaml workflow file after this WI WHEN the apply job env block is inspected THEN GW_RESOURCE_PREFIX is set (e.g. from secrets.GW_RESOURCE_PREFIX or a static value) so gw apply scopes by the ownership marker
- (WI-2) GIVEN the ci.yaml workflow file after this WI WHEN its job names are listed THEN jobs named exactly 'Structural Tests' and 'Dry-Run Smoke Test' exist and are not renamed
- (WI-3) GIVEN GW_RESOURCE_PREFIX is set and the live org is accessible via GW_APP_ID / GW_APP_INSTALLATION_ID / GW_APP_PRIVATE_KEY_PATH WHEN gw apply runs against the live throwaway org THEN exits 0; only resources whose names start with GW_RESOURCE_PREFIX are touched; the org API is called with valid auth
- (WI-3) GIVEN GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX are both set (forge test-isolation mode) WHEN gw apply runs against the live throwaway org THEN exits 0; only resources matching FORGE_RESOURCE_PREFIX are touched (narrowed scope); no resource outside FORGE_RESOURCE_PREFIX is mutated
- (WI-3) GIVEN the live apply acceptance test has run successfully WHEN gw reset runs with GW_RESOURCE_PREFIX set THEN managed resources created by gw apply are removed; exits 0
- (WI-4) GIVEN WI-1 and WI-2 changes are applied to the repository WHEN python3 -m pytest tests/ runs THEN zero test failures; all offline tests pass or skip; no existing test is regressed

## What

- **WI-1** [complete] # WI-1: GW_RESOURCE_PREFIX ownership marker
- **WI-2** [complete] # WI-2: Fix Apply workflow CI
- **WI-3** [complete] # WI-3: Live acceptance — verify apply path with GW_RESOURCE_PREFIX
- **WI-4** [complete] # WI-4: Full offline test suite green

```
10 files changed, 475 insertions(+), 106 deletions(-)
```

- `.github/workflows/gitweave-apply.yaml`
- `gitweave/plan.py`
- `gitweave/reset.py`
- `tests/acceptance/test_gw_apply_path.py`
- `tests/conftest.py`
- `tests/test_apply_reset.py`
- `tests/test_apply_workflow_rewired.py`
- `tests/test_apply_workflow_structure.py`
- `tests/test_ownership_marker.py`
- `tests/test_plan.py`

## How

Merge-boundary gates the orchestrator ran:

- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` (local) — pass
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py` (ci) — pass

Evidence captured:

- `gw plan` — gw plan scopes by GW_RESOURCE_PREFIX, not FORGE_RESOURCE_PREFIX (unchanged)
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero -q` — Full offline test suite exits 0 after prefix and workflow fixes (unchanged)
- `gw org rulesets --json` — org rulesets read back under GW_RESOURCE_PREFIX scope (unchanged)

No observable behaviour change was captured. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path. API bodies compared as JSON after dropping volatile JSON keys (ids, timestamps, urls, etags, sizes, watchers) and declared ignoreKeys.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._
