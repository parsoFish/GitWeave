# I3a — Green Apply Path

Initiative `INIT-2026-10-11-i3a-green-apply-path` · project `gitweave` · head `15c00467c9dc7e241cd80aec3952aed6171f9dae`

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
- (WI-5) GIVEN FORGE_RESOURCE_PREFIX explicitly unset in the test process (monkeypatch.delenv or env -u) and GW_RESOURCE_PREFIX set WHEN `gw plan`, `gw apply` and `gw reset` run THEN all three succeed and scope every resource decision by GW_RESOURCE_PREFIX; every manager (teams, repos, rulesets, org) uses GitWeave's marker and none references FORGE_RESOURCE_PREFIX as a requirement
- (WI-5) GIVEN FORGE_RESOURCE_PREFIX is set WHEN any gw command runs THEN it must start with GW_RESOURCE_PREFIX and only narrows the scope; a value that does not start with it is refused by name and nothing is changed
- (WI-5) GIVEN the throwaway org after `gw apply` WHEN `gw reset` runs THEN an API read-back (GET of teams, repos and rulesets) shows no resource carrying the GitWeave marker remains — not exit code alone
- (WI-5) GIVEN the test suite WHEN it is read THEN no autouse fixture sets FORGE_RESOURCE_PREFIX for every test; tests that need it set it explicitly
- (WI-5) GIVEN the PR head WHEN GitHub Actions runs THEN the GitWeave Apply workflow runs on the PR (its path filter covers gitweave/** and the workflow file) and every job, including the live gw apply, is green; Structural Tests and Dry-Run Smoke Test stay green

## What

- **WI-1** [complete] # WI-1: GW_RESOURCE_PREFIX ownership marker
- **WI-2** [complete] # WI-2: Fix Apply workflow CI
- **WI-3** [complete] # WI-3: Live acceptance — verify apply path with GW_RESOURCE_PREFIX
- **WI-4** [complete] # WI-4: Full offline test suite green
- **WI-5** [complete] # WI-5 — review-fix concern (code-fix)

```
44 files changed, 1153 insertions(+), 159 deletions(-)
```

- `.github/workflows/gitweave-apply.yaml`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.filmstrip.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.out`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.png`
- `demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.webm`
- `demo/INIT-2026-10-11-i3a-green-apply-path/DEMO.md`
- `demo/INIT-2026-10-11-i3a-green-apply-path/demo-plan.json`
- `demo/INIT-2026-10-11-i3a-green-apply-path/demo.json`
- `gitweave.egg-info/SOURCES.txt`
- `gitweave/managers/repos.py`
- `gitweave/managers/rulesets.py`
- `gitweave/managers/teams.py`
- `gitweave/plan.py`
- `gitweave/reset.py`
- `tests/acceptance/test_gw_apply_path.py`
- `tests/acceptance/test_gw_reset_before_apply.py`
- `tests/acceptance/test_gw_workflow.py`
- `tests/conftest.py`
- `tests/test_apply_reset.py`
- `tests/test_apply_workflow_rewired.py`
- `tests/test_apply_workflow_structure.py`
- `tests/test_manager_resources.py`
- `tests/test_ownership_marker.py`
- `tests/test_plan.py`

## How

Merge-boundary gates the orchestrator ran:

- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` (local) — pass
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py` (ci) — pass

Evidence captured:

- `gw plan` — gw plan succeeds with GW_RESOURCE_PREFIX alone (unchanged)
- `gw apply --json` — gw apply scopes resources by GW_RESOURCE_PREFIX (unchanged)
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero -q` — Offline test suite exits zero (unchanged)
- Plan-1-WI-1-1yki11 — Plan-1-WI-1-1yki11 (changed)
- Plan-2-WI-4-e7s9a2 — Plan-2-WI-4-e7s9a2 (changed)
- Plan-3-WI-2-sw6ji1 — Plan-3-WI-2-sw6ji1 (changed)

3 of 6 captured checkpoints changed behaviour. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path. API bodies compared as JSON after dropping volatile JSON keys (ids, timestamps, urls, etags, sizes, watchers) and declared ignoreKeys.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._

---

## Demo

▶ **[Open the rendered demo: `demo/INIT-2026-10-11-i3a-green-apply-path/DEMO.md`](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/DEMO.md)** — renders inline on GitHub (works for private repos too).

The screenshots are also visible in this PR's **Files changed** tab (committed under `demo/INIT-2026-10-11-i3a-green-apply-path/`).

Demo artefacts:
- [`DEMO.md`](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/DEMO.md)
- [`demo-plan.json`](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/demo-plan.json)
- [`demo.json`](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/demo.json)


### Captured checkpoints

**Plan-1-WI-1-1yki11**

![Plan-1-WI-1-1yki11 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.filmstrip.png?raw=true)

![Plan-1-WI-1-1yki11 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.filmstrip.png?raw=true)

[▶ Plan-1-WI-1-1yki11 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-1-1yki11.webm)

[▶ Plan-1-WI-1-1yki11 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-1-1yki11.webm)

**Plan-1-WI-5-1yki11**

![Plan-1-WI-5-1yki11 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-5-1yki11.filmstrip.png?raw=true)

![Plan-1-WI-5-1yki11 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-5-1yki11.filmstrip.png?raw=true)

[▶ Plan-1-WI-5-1yki11 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-1-WI-5-1yki11.webm)

[▶ Plan-1-WI-5-1yki11 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-1-WI-5-1yki11.webm)

**Plan-2-WI-4-e7s9a2**

![Plan-2-WI-4-e7s9a2 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.filmstrip.png?raw=true)

![Plan-2-WI-4-e7s9a2 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.filmstrip.png?raw=true)

[▶ Plan-2-WI-4-e7s9a2 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-4-e7s9a2.webm)

[▶ Plan-2-WI-4-e7s9a2 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-4-e7s9a2.webm)

**Plan-2-WI-5-e7s9a3**

![Plan-2-WI-5-e7s9a3 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-5-e7s9a3.filmstrip.png?raw=true)

![Plan-2-WI-5-e7s9a3 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-5-e7s9a3.filmstrip.png?raw=true)

[▶ Plan-2-WI-5-e7s9a3 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-2-WI-5-e7s9a3.webm)

[▶ Plan-2-WI-5-e7s9a3 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-2-WI-5-e7s9a3.webm)

**Plan-3-WI-2-sw6ji1**

![Plan-3-WI-2-sw6ji1 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.filmstrip.png?raw=true)

![Plan-3-WI-2-sw6ji1 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.filmstrip.png?raw=true)

[▶ Plan-3-WI-2-sw6ji1 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-2-sw6ji1.webm)

[▶ Plan-3-WI-2-sw6ji1 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-2-sw6ji1.webm)

**Plan-3-WI-4-sw6ji3**

![Plan-3-WI-4-sw6ji3 — before](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-4-sw6ji3.filmstrip.png?raw=true)

![Plan-3-WI-4-sw6ji3 — after](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-4-sw6ji3.filmstrip.png?raw=true)

[▶ Plan-3-WI-4-sw6ji3 — before (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/before/Plan-3-WI-4-sw6ji3.webm)

[▶ Plan-3-WI-4-sw6ji3 — after (webm)](https://github.com/parsoFish/GitWeave/blob/a141e6ef66c4c1ab81aa3c16822ec5c9785f86a0/demo/INIT-2026-10-11-i3a-green-apply-path/.capture/after/Plan-3-WI-4-sw6ji3.webm)

