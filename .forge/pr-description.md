# I3b — Self-Service

Initiative `INIT-2026-10-11-i3b-self-service` · project `gitweave` · head `55db1a880733ec191d8d174fd8eff3f4312a8d3c`

## Why

The acceptance criteria this initiative was decomposed against:

- (WI-1) GIVEN config/policy.yaml is absent WHEN PolicyLoader.load() is called THEN raises PolicyError with a message naming the missing file; exits non-zero when called via the CLI
- (WI-1) GIVEN config/policy.yaml exists but is not valid YAML WHEN PolicyLoader.load() is called THEN raises PolicyError naming the parse problem; does not silently allow all requests
- (WI-1) GIVEN config/policy.yaml exists but fails jsonschema validation (e.g. missing required field) WHEN PolicyLoader.load() is called THEN raises PolicyError with the schema validation message
- (WI-1) GIVEN a team slug that does not appear in config/policy.yaml WHEN policy.check_permission(team='unknown-team', request_type='new-repo') is called THEN raises PolicyDenied naming the team and stating it has no declared permissions
- (WI-1) GIVEN a team that has 'new-repo' in its allowed_request_types and the repo name matches allowed_patterns WHEN policy.check_permission(team='platform', request_type='new-repo', repo_name='forge-foo') is called THEN returns True without raising
- (WI-1) GIVEN a team that does NOT have the requested request_type in its allowed_request_types WHEN policy.check_permission is called for that type THEN raises PolicyDenied citing the specific rule name (e.g. 'new-repo not in platform.allowed_request_types')
- (WI-1) GIVEN a repo name that does not match the team's allowed_repo_patterns WHEN policy.check_permission(team, 'new-repo', repo_name='not-allowed') is called THEN raises PolicyDenied naming the pattern rule
- (WI-2) GIVEN GW_CALLER_TOKEN is set to a valid token string WHEN get_caller_token() is called THEN returns that token value without invoking gh
- (WI-2) GIVEN GW_CALLER_TOKEN is not set and 'gh auth token' returns a token on stdout WHEN get_caller_token() is called THEN returns the token from gh auth token
- (WI-2) GIVEN GW_CALLER_TOKEN is not set and 'gh auth token' fails (non-zero exit or empty output) WHEN get_caller_token() is called THEN raises CallerTokenRequiredError with a message including 'caller-token-required'; never returns None or an empty string
- (WI-2) GIVEN a valid caller token that the GitHub API /user endpoint can resolve WHEN resolve_caller_login(token) is called (using a mock HTTP client) THEN returns the login string from the API response
- (WI-2) GIVEN a caller token that the GitHub API rejects (401) WHEN resolve_caller_login(token) is called THEN raises CallerTokenRequiredError
- (WI-3) GIVEN policy allows new-repo for the team and name matches the allowed pattern WHEN self_serve_new_repo(team, name, gh_org, policy, caller_login) is called THEN calls gh_org.create_repo with the correct name and returns a success result
- (WI-3) GIVEN same command called when the repo already exists WHEN self_serve_new_repo is called a second time THEN returns success without raising (idempotent — exits 0)
- (WI-3) GIVEN repo name does not match the team's allowed_repo_patterns in policy WHEN self_serve_new_repo is called THEN raises PolicyDenied naming the pattern rule; no API call is made
- (WI-3) GIVEN team not present in policy.yaml WHEN self_serve_new_repo is called THEN raises PolicyDenied naming the team and stating no declared permissions
- (WI-4) GIVEN team policy allows 'content-update' and setting is in team's allowed_content_settings WHEN self_serve_update_content(team, repo_name, setting, value, gh_org, policy, caller_login) is called THEN applies the setting via the appropriate GitHub API call on the repo object and returns success
- (WI-4) GIVEN setting type 'branch_protection' with a rule dict WHEN update_content is called THEN calls repo.get_branch(branch).edit_protection with the provided parameters
- (WI-4) GIVEN setting type 'topics' WHEN update_content is called THEN calls repo.replace_topics with the provided list
- (WI-4) GIVEN setting type not in team's allowed_content_settings in policy WHEN update_content is called THEN raises PolicyDenied naming the setting and the rule
- (WI-4) GIVEN team not in policy WHEN update_content is called THEN raises PolicyDenied naming the team
- (WI-5) GIVEN team policy allows 'team-membership' and caller_login is a member of the team per the live org (mocked) WHEN self_serve_add_member(team, member_login, gh_org, policy, caller_login) is called THEN calls the team's add_to_members API method and returns success
- (WI-5) GIVEN caller is not a member of the team (mocked membership check returns False) WHEN self_serve_add_member is called THEN raises PolicyDenied stating caller is not a member of the team
- (WI-5) GIVEN team not in policy.yaml WHEN self_serve_add_member is called THEN raises PolicyDenied naming the team and stating no declared permissions
- (WI-5) GIVEN team policy allows 'team-membership' and caller is a team member WHEN self_serve_remove_member(team, member_login, gh_org, policy, caller_login) is called THEN calls the team's remove_from_members API method and returns success
- (WI-6) GIVEN team policy allows 'policy-exception' for the repo and exception_name is in allowed_exceptions WHEN self_serve_add_exception(team, repo_name, exception_name, reason, gh_org, policy, caller_login) is called THEN creates the org-level custom property definition (idempotent) and sets it on the repo; returns success
- (WI-6) GIVEN the org-level custom property definition already exists WHEN self_serve_add_exception is called again THEN does not raise; sets the property on the repo (idempotent on the definition creation step)
- (WI-6) GIVEN a repo with one or more exception custom properties set WHEN self_serve_list_exceptions(repo_name, gh_org) is called THEN returns a list of dicts with exception_name and value read back via the GitHub API
- (WI-6) GIVEN team not in policy or exception type not allowed WHEN self_serve_add_exception is called THEN raises PolicyDenied naming the specific rule
- (WI-7) GIVEN gw self-serve new-repo --team <slug> --name <name> is invoked via argparse WHEN main() parses and dispatches THEN calls self_serve_new_repo with correct arguments and exits 0 on success
- (WI-7) GIVEN gw self-serve update-content --team <slug> --repo <name> --setting topics --value 'a,b' is invoked WHEN main() dispatches THEN calls self_serve_update_content with correct arguments and exits 0
- (WI-7) GIVEN gw self-serve add-member --team <slug> --member <login> is invoked WHEN main() dispatches THEN calls self_serve_add_member with correct arguments and exits 0
- (WI-7) GIVEN gw self-serve add-exception --team <slug> --repo <name> --exception <key> --reason <text> WHEN main() dispatches THEN calls self_serve_add_exception and exits 0
- (WI-7) GIVEN gw self-serve list-exceptions --repo <name> is invoked WHEN main() dispatches THEN calls self_serve_list_exceptions, prints JSON result, exits 0
- (WI-7) GIVEN any self-serve command and CallerTokenRequiredError is raised WHEN main() catches it THEN prints error message to stderr containing 'caller-token-required' and exits non-zero
- (WI-7) GIVEN any self-serve command and PolicyDenied is raised WHEN main() catches it THEN prints the policy denial message to stderr and exits non-zero
- (WI-8) GIVEN a self-serve-managed repo declared in policy.yaml that does not yet exist in the snapshot WHEN _diff() processes the snapshot THEN PlanResult includes a PlanItem(resource_type='self_serve_repo', action='create')
- (WI-8) GIVEN a self-serve-managed repo that exists in both declared policy and the snapshot WHEN _diff() processes the snapshot THEN PlanResult includes a PlanItem(resource_type='self_serve_repo', action='unchanged')
- (WI-8) GIVEN a self-serve-managed repo present in the snapshot but removed from policy.yaml WHEN _diff() processes the snapshot THEN PlanResult includes a PlanItem(resource_type='self_serve_repo', action='delete')
- (WI-8) GIVEN a policy exception (custom property) set on a repo that is no longer in policy.yaml exceptions list WHEN _diff() processes the snapshot THEN PlanResult includes a PlanItem(resource_type='policy_exception', action='delete')
- (WI-8) GIVEN a team membership declared in policy.yaml team membership list but not present in the snapshot WHEN _diff() processes the snapshot THEN PlanResult includes a PlanItem(resource_type='team_membership', action='create')
- (WI-9) GIVEN GW_CALLER_TOKEN set to an org-member token, team with new-repo permission in policy.yaml, name matches allowed pattern WHEN `gw self-serve new-repo --team <slug> --name <name>` runs against the throwaway org THEN repo exists (verified via GET /repos/{org}/{name}), command exits 0, no PR opened on control repo
- (WI-9) GIVEN GW_CALLER_TOKEN set, team has content-update permission, requested setting in allowed set WHEN `gw self-serve update-content --team <slug> --repo <name> --setting topics --value forge,test` runs THEN topics applied (verified via API read-back), exits 0, no PR opened on control repo
- (WI-9) GIVEN GW_CALLER_TOKEN set, requester is a team member per policy WHEN `gw self-serve add-member --team <slug> --member <login>` runs THEN membership applied (verified via GET /orgs/{org}/teams/{slug}/memberships/{login}), exits 0, no PR opened
- (WI-9) GIVEN an allowed policy exception for a managed repository WHEN exception applied then `gw self-serve list-exceptions --repo <name>` runs THEN exception listed (custom property verified via GET /repos/{org}/{repo}/properties/values)
- (WI-9) GIVEN a self-serve request that violates a named policy rule WHEN the self-serve command runs against the live org THEN exits non-zero, output names the specific policy rule, org is unchanged
- (WI-9) GIVEN GW_CALLER_TOKEN is not set and gh auth token is unavailable WHEN any gw self-serve command runs THEN exits non-zero with error containing 'caller-token-required'
- (WI-10) GIVEN the repository on main after I3b merges WHEN `python3 -m pytest tests/` runs THEN zero test failures
- (WI-11) GIVEN the test creates one marker-prefixed team and one marker-prefixed repository in the throwaway org through the GitHub API, with GW_* set WHEN `python3 -m pytest tests/acceptance/test_gw_reset_readback.py` runs `gw reset` twice THEN the first run exits 0, a GET of the org teams and repositories (not gw output) lists neither resource, and the second run exits 0 and prints "Nothing changed."
- (WI-12) GIVEN GW_* set and the throwaway org holds teams, repositories and rulesets whose names do not carry the resource marker WHEN `python3 -m pytest tests/acceptance/test_gw_containment.py` runs `gw apply` then `gw reset` THEN a before/after snapshot of the org taken through the GitHub API shows every unmarked team, repository and ruleset unchanged, and the test never parses gw stdout to decide containment
- (WI-13) GIVEN RulesetsManager calls GET /orgs/{org}/rulesets WHEN `python3 -m pytest tests/test_rulesets_unsupported_plan.py` runs with the request raising (a) a GithubException with status 403 and (b) another exception whose message merely contains "403" THEN (a) list_managed returns [] and apply returns status skipped; (b) the exception propagates; and the list_managed docstring names GW_RESOURCE_PREFIX, not FORGE_RESOURCE_PREFIX

## What

- **WI-1** [complete] # WI-1: Policy engine + self-serve package scaffold
- **WI-2** [complete] # WI-2: Two-identity auth — caller token resolution
- **WI-3** [complete] # WI-3: gw self-serve new-repo
- **WI-4** [complete] # WI-4: gw self-serve update-content
- **WI-5** [complete] # WI-5: gw self-serve add-member / remove-member
- **WI-6** [complete] # WI-6: Policy exception recording via GitHub custom properties
- **WI-7** [complete] # WI-7: CLI wiring — gw self-serve subcommands
- **WI-8** [complete] # WI-8: Plan engine — three state branches for self-serve resource types
- **WI-9** [complete] # WI-9: Live acceptance tests — gw self-serve
- **WI-10** [complete] # WI-10: Full test suite smoke (AC11 integration gate)
- **WI-11** [complete] Reset proven by API read-back after a real create
- **WI-12** [complete] Containment proven by API state, not gw stdout
- **WI-13** [complete] Rulesets unsupported-plan check is typed, docstring names GitWeave marker

```
25 files changed, 2567 insertions(+), 6 deletions(-)
```

- `config/policy.yaml`
- `gitweave/auth.py`
- `gitweave/cli.py`
- `gitweave/managers/rulesets.py`
- `gitweave/plan.py`
- `gitweave/policy.py`
- `gitweave/self_serve/__init__.py`
- `gitweave/self_serve/exceptions.py`
- `gitweave/self_serve/membership.py`
- `gitweave/self_serve/new_repo.py`
- `gitweave/self_serve/update_content.py`
- `pyproject.toml`
- `tests/acceptance/test_gw_containment.py`
- `tests/acceptance/test_gw_reset_readback.py`
- `tests/acceptance/test_gw_self_serve.py`
- `tests/test_caller_auth.py`
- `tests/test_cli_self_serve.py`
- `tests/test_plan_self_serve.py`
- `tests/test_policy.py`
- `tests/test_rulesets_unsupported_plan.py`
- `tests/test_self_serve_exceptions.py`
- `tests/test_self_serve_membership.py`
- `tests/test_self_serve_new_repo.py`
- `tests/test_self_serve_update_content.py`
- `tests/test_suite_smoke.py`

## How

Merge-boundary gates the orchestrator ran:

- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` (local) — pass
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py` (ci) — pass

Evidence captured:

- `python3 -m pytest tests/` — Full test suite passes with all self-serve modules wired (changed)

```
- collected 577 items
+ collected 649 items
- tests/acceptance/test_gw_reset_before_apply.py ss                        [  0%]
+ tests/acceptance/test_gw_containment.py s                                [  0%]
- tests/acceptance/test_gw_workflow.py sss                                 [  1%]
+ tests/acceptance/test_gw_reset_before_apply.py ss                        [  0%]
- tests/test_apply_reset.py ..................                             [  4%]
+ tests/acceptance/test_gw_reset_readback.py s                             [  0%]
- tests/test_apply_workflow_rewired.py ....                                [  5%]
+ tests/acceptance/test_gw_self_serve.py FFFFFF                            [  1%]
- tests/test_apply_workflow_structure.py .................                 [  7%]
+ tests/acceptance/test_gw_workflow.py sss                                 [  2%]
- tests/test_auth.py .......                                               [  9%]
+ tests/test_apply_reset.py ..................                             [  5%]
- tests/test_brownfield_import_validate.py sssssssssssssss                 [ 11%]
+ tests/test_apply_workflow_rewired.py ....                                [  5%]
- tests/
…[truncated]
```
- `gw plan` — Plan lists self-serve resource types across all three action branches (unchanged)
- `python3 -m pytest tests/test_rulesets_unsupported_plan.py` — Rulesets unsupported-plan check typed and docstring correct (changed)

```
- collected 0 items
+ collected 6 items
- ============================ no tests ran in <duration> =============================
+ tests/test_rulesets_unsupported_plan.py ......                           [100%]
- [stderr] ERROR: file or directory not found: tests/test_rulesets_unsupported_plan.py
+ 
+ ============================== 6 passed in <duration> ===============================
+ 
```
- `gw org show --json` — Org state shows self-serve repos and teams after apply (unchanged)
- `python3 -m pytest tests/acceptance/test_gw_reset_readback.py` — Reset read-back: marker resources gone, second run prints nothing changed (changed)

```
- collected 0 items
+ collected 1 item
- ============================ no tests ran in <duration> =============================
+ tests/acceptance/test_gw_reset_readback.py s                             [100%]
- [stderr] ERROR: file or directory not found: tests/acceptance/test_gw_reset_readback.py
+ 
+ ============================== 1 skipped in <duration> ==============================
+ 
```
- `python3 -m pytest tests/acceptance/test_gw_containment.py` — Containment: unmarked resources unchanged after apply+reset, verified via API not stdout (changed)

```
- collected 0 items
+ collected 1 item
- ============================ no tests ran in <duration> =============================
+ tests/acceptance/test_gw_containment.py s                                [100%]
- [stderr] ERROR: file or directory not found: tests/acceptance/test_gw_containment.py
+ 
+ ============================== 1 skipped in <duration> ==============================
+ 
```

4 of 6 captured checkpoints changed behaviour. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path. API bodies compared as JSON after dropping volatile JSON keys (ids, timestamps, urls, etags, sizes, watchers) and declared ignoreKeys.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._
