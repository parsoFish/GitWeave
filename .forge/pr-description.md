# I2 — Apply engine, Terraform retired

Initiative `INIT-2026-10-11-i2-apply-engine-terraform-retired` · project `gitweave` · head `c772a56a3159d6cd3f928b7939d7f7df266b42d6`

## Why

The acceptance criteria this initiative was decomposed against:

- (WI-1) GIVEN a clean checkout with no gitweave package installed WHEN pip install -e . runs from the repo root THEN exits 0 and the gw entry point is registered on PATH
- (WI-1) GIVEN the installed package WHEN python3 -c 'import gitweave; from gitweave.cli import main' runs THEN exits 0 with no ImportError
- (WI-1) GIVEN the installed package WHEN gw --help runs THEN exits 0 and prints usage with at least the plan, apply, reset verbs listed
- (WI-2) GIVEN GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG are all set WHEN gitweave.auth.get_github_client() is called THEN returns a PyGithub Github object authenticated as the installation
- (WI-2) GIVEN any one of GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG is unset WHEN gitweave.auth.get_github_client() is called THEN raises EnvironmentError naming the missing variable
- (WI-2) GIVEN GW_APP_PRIVATE_KEY_PATH points to a file that does not exist WHEN gitweave.auth.get_github_client() is called THEN raises FileNotFoundError or EnvironmentError with a descriptive message
- (WI-3a) GIVEN schemas/org.schema.json exists WHEN python3 loads it as JSON THEN exits 0 — valid JSON with required, properties, additionalProperties fields
- (WI-3a) GIVEN schemas/teams.schema.json exists WHEN python3 loads it as JSON THEN exits 0 — valid JSON with a 'teams' array property
- (WI-3a) GIVEN schemas/org-ruleset.schema.json exists WHEN python3 loads it as JSON THEN exits 0 — valid JSON with a 'rulesets' array property
- (WI-3b) GIVEN tests/fixtures/org-empty.json exists WHEN the file is parsed as JSON THEN it represents an empty org state with keys: org_settings, teams, repos, rulesets all present as empty collections
- (WI-3b) GIVEN schemas/org.schema.json exists and config/org.yaml exists WHEN jsonschema validates config/org.yaml against schemas/org.schema.json THEN exits 0 with no validation errors
- (WI-3b) GIVEN schemas/teams.schema.json exists and config/teams.yaml exists WHEN jsonschema validates config/teams.yaml against schemas/teams.schema.json THEN exits 0 with no validation errors
- (WI-3b) GIVEN schemas/org-ruleset.schema.json exists and config/rulesets.yaml exists WHEN jsonschema validates config/rulesets.yaml against schemas/org-ruleset.schema.json THEN exits 0 with no validation errors
- (WI-4) GIVEN config/org.yaml, config/teams.yaml, config/rulesets.yaml exist WHEN gitweave.config.load_config() is called from the repo root THEN returns a dict with keys org_settings, teams, repos, rulesets; each validated against its JSON schema
- (WI-4) GIVEN a config/org.yaml with an invalid field (e.g. default_repository_permission: invalid) WHEN gitweave.config.load_config() is called THEN raises jsonschema.ValidationError identifying the invalid field
- (WI-4) GIVEN config/org.yaml is missing WHEN gitweave.config.load_config() is called THEN raises FileNotFoundError with a descriptive message
- (WI-5a) GIVEN a mocked Github client and org_settings config dict WHEN OrgSettingsManager.apply(org_settings) is called THEN calls org.edit() with the declared settings and returns status ok
- (WI-5a) GIVEN an org already at GitHub safe defaults WHEN OrgSettingsManager.reset() is called THEN calls org.edit() with description='', default_repository_permission='read', web_commit_signoff_required=False, members_can_create_repositories=True
- (WI-5a) GIVEN org.edit() raises a GitHub API exception WHEN OrgSettingsManager.apply() is called THEN returns status error with the exception message rather than propagating
- (WI-5b) GIVEN FORGE_RESOURCE_PREFIX is set and a mocked Github org WHEN TeamsManager.list_managed() is called THEN returns only teams whose name starts with FORGE_RESOURCE_PREFIX
- (WI-5b) GIVEN a team config entry and mocked Github org WHEN TeamsManager.apply(team_config) is called and team does not exist THEN calls org.create_team() and returns ResourceStatus(status='ok')
- (WI-5b) GIVEN FORGE_RESOURCE_PREFIX is unset or empty WHEN any of TeamsManager, ReposManager, RulesetsManager is instantiated THEN raises EnvironmentError naming FORGE_RESOURCE_PREFIX
- (WI-5b) GIVEN a repo slug not yet present in the org WHEN ReposManager.apply(repo_config) is called THEN calls org.create_repo() with the declared settings and returns status ok
- (WI-5b) GIVEN a ruleset not yet present and mocked Github org WHEN RulesetsManager.apply(ruleset_config) is called THEN calls the org rulesets API and returns status ok
- (WI-6) GIVEN tests/fixtures/org-empty.json exists and config declares teams + rulesets WHEN plan(fixture_path='tests/fixtures/org-empty.json') is called THEN returns a PlanResult with all declared resources listed as 'create' actions and makes zero network calls
- (WI-6) GIVEN the fixture represents an org that already has all declared resources WHEN plan(fixture_path=...) is called THEN returns a PlanResult with all resources listed as 'unchanged'
- (WI-6) GIVEN both fixture_path is provided AND GW_* env vars are set WHEN plan(fixture_path=...) is called THEN uses the fixture exclusively — no network calls — fixture and live auth are mutually exclusive
- (WI-6) GIVEN GW_ORG is unset and no fixture_path provided WHEN plan() is called THEN raises EnvironmentError naming GW_ORG
- (WI-7) GIVEN GW_* set and a mocked Github org with no managed resources WHEN apply(json_mode=False) is called THEN calls each manager's apply() for every declared resource; returns ApplyResult with per-resource status
- (WI-7) GIVEN one resource apply fails mid-run (manager returns status='error') WHEN apply() is called THEN continues applying remaining resources (best-effort), exits non-zero, reports per-resource status including the failure
- (WI-7) GIVEN GW_* set WHEN apply(json_mode=True) is called THEN first calls reset() to delete all prefixed resources, then applies the full declaration, then returns JSON-serialisable state dict
- (WI-7) GIVEN a mocked org with prefixed resources only WHEN reset() is called THEN deletes every prefixed team/repo/ruleset and restores org settings to safe defaults; 404s treated as success
- (WI-7) GIVEN a mocked org already at defaults with no prefixed resources WHEN reset() is called twice THEN both calls exit 0 and the second reports nothing changed
- (WI-8) GIVEN GW_ORG is unset and --fixture is not provided WHEN gw plan runs THEN exits non-zero and stderr contains 'GW_ORG'
- (WI-8) GIVEN tests/fixtures/org-empty.json exists WHEN gw plan --fixture tests/fixtures/org-empty.json runs THEN exits 0 and stdout contains at least one + create line
- (WI-8) GIVEN GW_* are set WHEN gw apply --json runs THEN exits 0 and stdout is valid JSON with 'statuses' and 'state' keys
- (WI-8) GIVEN GW_* are set WHEN gw reset runs THEN exits 0
- (WI-8) GIVEN the installed package WHEN gw org show --json runs with GW_* set THEN exits 0 and stdout is valid JSON
- (WI-8) GIVEN the installed package WHEN gw --help runs THEN exits 0 and all verbs (plan, apply, reset, org) appear in output
- (WI-9a) GIVEN the worktree after WI-9a completes WHEN find infra/ is run THEN the infra/ directory does not exist
- (WI-9a) GIVEN the worktree after WI-9a completes WHEN ls .github/workflows/gitweave-infra.yaml is run THEN the file does not exist
- (WI-9a) GIVEN git prereq present and python3 present WHEN bash scripts/bootstrap.sh runs from the repo root THEN exits 0 — no Terraform check, pip install -e . succeeds
- (WI-9a) GIVEN hashicorp/setup-terraform@v3 is absent from ci.yaml WHEN grep 'setup-terraform' .github/workflows/ci.yaml runs THEN returns no matches
- (WI-9a) GIVEN the repository after I2 merges WHEN it is read and python3 -m pytest tests/ runs THEN infra/ and every Terraform file and workflow are absent, and pytest reports zero failures
- (WI-9b) GIVEN schemas/teams.schema.json and config/teams.yaml exist WHEN test_teams_yaml_validates_against_schema runs THEN passes — config/teams.yaml conforms to the schema
- (WI-9b) GIVEN tests/fixtures/org-empty.json and the gw CLI installed WHEN gw plan --fixture tests/fixtures/org-empty.json runs THEN exits 0 and stdout contains at least one '+ create' line for each declared resource type
- (WI-9b) GIVEN no TF team test files remain WHEN find tests/ -name 'test_tf_teams_*.py' runs THEN returns no results (all TF team tests are deleted)
- (WI-10) GIVEN .github/workflows/gitweave-apply.yaml after WI-10 WHEN the file is parsed as YAML THEN it is valid YAML with a pull_request trigger running 'gw plan --fixture' and a push-to-main trigger running 'gw apply'
- (WI-10) GIVEN the rewritten workflow WHEN grep 'gw plan --fixture' .github/workflows/gitweave-apply.yaml runs THEN returns a match — the PR job uses fixture-mode plan
- (WI-10) GIVEN the rewritten workflow WHEN grep 'GW_APP_PRIVATE_KEY' .github/workflows/gitweave-apply.yaml runs THEN the key is written to a temp file (mktemp pattern) and never echoed or logged
- (WI-10) GIVEN the existing dry-run-smoke job in gitweave-apply.yaml WHEN the workflow is inspected THEN the dry-run-smoke job and apply-overlays.py references are unchanged (I4 scope)
- (WI-11) GIVEN README.md and docs/demo-guide.md after WI-11 WHEN grep -in 'terraform' README.md docs/demo-guide.md runs THEN returns no matches — all Terraform references removed
- (WI-11) GIVEN README.md after WI-11 WHEN grep -in 'infra/' README.md runs THEN returns no matches — infra/ directory references removed
- (WI-11) GIVEN README.md after WI-11 WHEN grep 'gw plan' README.md runs THEN returns a match — gw usage is documented
- (WI-11) GIVEN docs/demo-guide.md after WI-11 WHEN grep 'gw apply' docs/demo-guide.md runs THEN returns a match — gw apply usage is documented in demo guide
- (WI-12) GIVEN GW_* set and the throwaway org after a gw apply run WHEN gw apply --json runs twice in sequence THEN both runs exit 0 and their JSON output is identical after stripping id, node_id, created_at, updated_at keys
- (WI-12) GIVEN the throwaway org after a gw apply run with GW_* set WHEN gw reset runs twice in sequence THEN both runs exit 0; the second run prints 'Nothing changed' and no resources matching FORGE_RESOURCE_PREFIX remain
- (WI-12) GIVEN tests/fixtures/org-empty.json exists and GW_* irrelevant (fixture mode) WHEN gw plan --fixture tests/fixtures/org-empty.json runs THEN exits 0 and stdout contains + create lines for each declared resource type with zero network calls
- (WI-13) GIVEN a FORGE_RESOURCE_PREFIX-named team that is NOT in the declaration exists in the throwaway org (created by the test via the API) and GW_* are set WHEN `python3 -m pytest tests/acceptance/test_gw_reset_before_apply.py` runs `gw apply --json` THEN the command exits 0 and that team is absent from both the printed JSON state and a read-back of the org (reset ran before apply)
- (WI-14) GIVEN the repository after I2 (infra/ removed) WHEN `python3 -m pytest tests/test_docs_no_terraform_tokens.py` runs THEN no file under docs/ and neither .github/copilot-context.md nor README.md contains the tokens terraform, infra/ or TF_ (case-insensitive)

## What

- **WI-1** [complete] # WI-1: Python package scaffold (pyproject.toml + gitweave entry point)
- **WI-2** [complete] # WI-2: GitHub App authentication module (gitweave/auth.py)
- **WI-3a** [complete] # WI-3a: JSON Schema files + seed config files
- **WI-3b** [complete] # WI-3b: Org-empty fixture + schema validation tests
- **WI-4** [complete] # WI-4: Config loading + validation module (gitweave/config.py)
- **WI-5a** [complete] # WI-5a: Org settings manager (gitweave/managers/org.py)
- **WI-5b** [complete] # WI-5b: Prefixed resource managers (teams, repos, rulesets)
- **WI-6** [failed] # WI-6: Plan engine — fixture + live diff (gitweave/plan.py)
- **WI-7** [complete] # WI-7: Apply + reset engines (gitweave/apply.py + gitweave/reset.py)
- **WI-8** [failed] # WI-8: CLI full wiring + read-back commands
- **WI-9a** [complete] # WI-9a: Terraform retirement + bootstrap rewrite + CI update
- **WI-9b** [failed] # WI-9b: gw-native team tests (replaces deleted TF team tests)
- **WI-10** [complete] # WI-10: Apply workflow rewrite (.github/workflows/gitweave-apply.yaml)
- **WI-11** [complete] # WI-11: Docs cleanup + terraform-retired assertion test
- **WI-12** [failed] # WI-12: Acceptance tests (live: apply idempotency + reset idempotency)
- **WI-13** [failed] Live proof that gw apply --json resets before applying
- **WI-14** [complete] No Terraform references left in agent context or docs

```
48 files changed, 1888 insertions(+), 3071 deletions(-)
```

- `.github/copilot-context.md`
- `.github/workflows/ci.yaml`
- `.github/workflows/gitweave-apply.yaml`
- `.github/workflows/gitweave-infra.yaml`
- `README.md`
- `config/org.yaml`
- `config/rulesets.yaml`
- `docs/demo-guide.md`
- `gitweave/__init__.py`
- `gitweave/apply.py`
- `gitweave/auth.py`
- `gitweave/cli.py`
- `gitweave/config.py`
- `gitweave/managers/__init__.py`
- `gitweave/managers/org.py`
- `gitweave/managers/repos.py`
- `gitweave/managers/rulesets.py`
- `gitweave/managers/teams.py`
- `gitweave/reset.py`
- `infra/bootstrap/README.md`
- `infra/branch_protection.tf`
- `infra/demo.tfvars.example`
- `infra/examples/branch_protection_override.tfvars`
- `infra/main.tf`
- `infra/outputs.tf`
- `infra/variables.tf`
- `pyproject.toml`
- `schemas/org-ruleset.schema.json`
- `schemas/org.schema.json`
- `schemas/teams.schema.json`
- `scripts/bootstrap.sh`
- `tests/fixtures/org-empty.json`
- `tests/test_apply_reset.py`
- `tests/test_auth.py`
- `tests/test_config.py`
- `tests/test_docs_no_terraform_tokens.py`
- `tests/test_docs_terraform_retired.py`
- `tests/test_gw_apply_workflow.py`
- `tests/test_gw_schemas.py`
- `tests/test_infra_workflow_gates.py`
- `tests/test_manager_org.py`
- `tests/test_manager_resources.py`
- `tests/test_package_structure.py`
- `tests/test_structure.py`
- `tests/test_terraform_demo_config.py`
- `tests/test_tf_teams_plan.py`
- `tests/test_tf_teams_structure.py`
- `tests/test_tf_teams_validate.py`

## How

Merge-boundary gates the orchestrator ran:

- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` (local) — pass
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py` (ci) — pass

Evidence captured:

- `git ls-files` — Terraform files absent; gw package present in tracked files (changed)

```
- .github/workflows/gitweave-infra.yaml
+ .github/workflows/module-calver.yaml
- .github/workflows/module-calver.yaml
+ .github/workflows/module-update-propagation.yaml
- .github/workflows/module-update-propagation.yaml
+ .github/workflows/overlay-validate.yaml
- .github/workflows/overlay-validate.yaml
+ .gitignore
- .gitignore
+ AGENTS.md
- AGENTS.md
+ CLA.md
- CLA.md
+ CLAUDE.md
- CLAUDE.md
+ LICENSE
- LICENSE
+ Makefile
- Makefile
+ README.md
- README.md
+ config/.gitkeep
- config/.gitkeep
+ config/example.yaml
- config/example.yaml
+ config/org.yaml
- config/teams.yaml
+ config/rulesets.yaml
- demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.filmstrip.png
+ config/teams.yaml
- demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.out
+ demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.filmstrip.png
- demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.webm
+ demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.out
- demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-10-WI-5-1rhlii.filmstrip.png
+ demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-W
…[truncated]
```
- `gw plan` — gw plan shows create actions for all declared resources against empty-org fixture (unchanged)
- `gw apply --json` — gw apply --json returns statuses + state dict after reset-before-apply (unchanged)
- `gw org show --json` — Org settings read back as JSON after apply (unchanged)
- `gw org teams --json` — Managed teams read back after apply (unchanged)
- `gw org rulesets --json` — Managed rulesets read back after apply (unchanged)
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero -q` — Structure + schema tests pass; no TF test files remain (changed)

```
- ........................................................................ [ 52%]
+ ........................................................................ [ 53%]
- .................................................................        [100%]
+ ...............................................................          [100%]
- 137 passed in <duration>
+ 135 passed, 1 deselected in <duration>
```
- `python3 -m pytest tests/test_docs_no_terraform_tokens.py` — No terraform tokens remain in docs or agent context (changed)

```
- rootdir: /home/parso/forge/_worktrees/INIT-2026-10-11-i2-apply-engine-terraform-retired
+ rootdir: <worktree>
- collected 0 items
+ collected 3 items
- ============================ no tests ran in <duration> =============================
+ tests/test_docs_no_terraform_tokens.py ...                               [100%]
- [stderr] ERROR: file or directory not found: tests/test_docs_no_terraform_tokens.py
+ 
+ ============================== 3 passed in <duration> ===============================
+ 
```
- `python3 -m pytest tests/acceptance/test_gw_reset_before_apply.py` — Reset-before-apply proof: stale prefixed team absent from state after apply --json (changed)

```
- rootdir: /home/parso/forge/_worktrees/INIT-2026-10-11-i2-apply-engine-terraform-retired
+ rootdir: <worktree>
```

4 of 9 captured checkpoints changed behaviour. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path. API bodies compared as JSON after dropping volatile JSON keys (ids, timestamps, urls, etags, sizes, watchers) and declared ignoreKeys.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._
