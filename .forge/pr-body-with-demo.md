# I3b — Self-Service

Initiative `INIT-2026-10-11-i3b-self-service` · project `gitweave` · head `104b99be0e32f4dd733f74e11a686214725233b0`

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
- (WI-14) GIVEN any live acceptance test under tests/acceptance/ and one of its required env vars (GW_APP_ID, GW_APP_PRIVATE_KEY_PATH, GW_APP_INSTALLATION_ID, GW_ORG, GW_CALLER_TOKEN, GW_RESOURCE_PREFIX) unset WHEN python3 -m pytest tests/acceptance is run THEN the test FAILS (or errors) naming the missing variable; no live acceptance test uses skipUnless/skip on credentials, and none is stubbed
- (WI-14) GIVEN GW_APP_*, GW_ORG=dave-parso, GW_CALLER_TOKEN and GW_RESOURCE_PREFIX=gw- set (the gate's requiresEnv) WHEN python3 -m pytest tests/ runs as this work item's gate THEN live tests for all four self-serve request types (new repo, content update, team membership, policy exception), reset proven by API read-back after a real create, and containment checked against API state each PASS against dave-parso; the gate output shows them passed and 0 skipped under tests/acceptance
- (WI-14) GIVEN the live acceptance tests create resources in the org WHEN they name and clean up those resources THEN every name derives from GW_RESOURCE_PREFIX (GitWeave's ownership marker); no test reads FORGE_RESOURCE_PREFIX or falls back to a hardcoded prefix
- (WI-14) GIVEN RulesetsManager.apply() meets a non-403 exception from the API WHEN gw apply runs THEN it returns ResourceStatus(status='error', error=...) (403 still → 'skipped'); tests/test_manager_resources.py::test_rulesets_apply_returns_error_on_exception passes; python3 -m pytest tests/ has 0 failures with GW_* and FORGE_* unset (live tier excluded by its env, not skipped silently)
- (WI-14) GIVEN a caller whose team policy.yaml does not permit the request type, name pattern, or target repo WHEN they run any gw self-serve command through the CLI THEN the CLI path calls check_permission() and refuses citing the policy rule; a permitted team can act only on repos within its declared scope (per-repo authorisation), proven by unit tests on the real CLI path
- (WI-14) GIVEN a fresh install of GitWeave from requirements.txt or pyproject.toml WHEN config/policy.yaml is loaded THEN jsonschema is declared in both requirements.txt and pyproject.toml and schema validation actually runs (a schema-invalid policy is rejected by jsonschema, not by the fallback path), proven by a test
- (WI-15) GIVEN tests/acceptance with GW_CALLER_TOKEN unset (the other GW_* set) WHEN python3 -m pytest tests/acceptance -q THEN the run FAILS naming GW_CALLER_TOKEN; no acceptance test uses skipUnless/skipTest/pytest.mark.skip on credentials
- (WI-15) GIVEN tests/acceptance with GW_RESOURCE_PREFIX unset (the other GW_* set) WHEN python3 -m pytest tests/acceptance -q THEN the run FAILS naming GW_RESOURCE_PREFIX
- (WI-15) GIVEN the gitweave package and the live acceptance tests WHEN searching gitweave/ and tests/acceptance/ for FORGE_RESOURCE_PREFIX or the 'gw-acc-' fallback THEN there is no match: every created resource name derives from GW_RESOURCE_PREFIX only (FORGE_RESOURCE_PREFIX is forge's gate-isolation var, not GitWeave's ownership marker)
- (WI-15) GIVEN a caller whose team policy.yaml does not permit the request type, name pattern or target repo WHEN python3 -m pytest tests/test_cli_check_permission.py -q THEN each gw self-serve CLI subcommand dispatch calls gitweave.policy.check_permission (asserted by spy, not by reimplemented inline checks) and the refusal message cites the denying rule; exit non-zero, nothing written to the org
- (WI-15) GIVEN a fresh install from requirements.txt or pyproject.toml WHEN python3 -m pytest tests/test_policy_jsonschema_required.py -q THEN jsonschema is declared in both files; policy.py imports jsonschema unconditionally (no ImportError fallback / minimal validation path); a schema-invalid policy.yaml is rejected with a ValidationError-derived PolicyError
- (WI-15) GIVEN the gw CLI WHEN python3 -m pytest tests/test_cli_remove_member.py -q THEN `gw self-serve remove-member` (or the documented subcommand name) is registered in the argparse tree and dispatches to self_serve_remove_member through check_permission
- (WI-15) GIVEN a missing or schema-invalid team policy.yaml WHEN python3 -m pytest tests/test_cli_policy_error.py -q THEN every self-serve CLI handler catches PolicyError (not only PolicyDenied) and exits non-zero with a one-line error naming the policy file; no traceback
- (WI-15) GIVEN a policy whose allowed_repo_patterns or allowed_exceptions is absent or empty WHEN python3 -m pytest tests/test_policy_fail_closed.py -q THEN check_permission and the allowed_exceptions guard DENY (fail closed) and name the empty list; nothing is permitted by absence

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
- **WI-14** [complete] # WI-14 — review-fix concern (code-fix)
- **WI-15** [complete] # WI-15 — review-fix concern (code-fix)

```
136 files changed, 4729 insertions(+), 306 deletions(-)
```

- `config/policy.yaml`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-10-1kq58o.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-10-1kq58o.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-10-1kq58o.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-10-1kq58o.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-8-e7s9a6.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-8-e7s9a6.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-8-e7s9a6.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-8-e7s9a6.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-9-17kktq.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-9-17kktq.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-9-17kktq.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-9-17kktq.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-11-tyf0zb.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-11-tyf0zb.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-11-tyf0zb.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-11-tyf0zb.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-12-1ms1i1.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-12-1ms1i1.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-12-1ms1i1.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-12-1ms1i1.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-9-1w9c77.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-9-1w9c77.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-9-1w9c77.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-6-WI-9-1w9c77.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-10-1kq58o.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-10-1kq58o.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-10-1kq58o.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-10-1kq58o.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-8-e7s9a6.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-8-e7s9a6.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-8-e7s9a6.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-8-e7s9a6.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-9-17kktq.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-9-17kktq.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-9-17kktq.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-9-17kktq.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-11-tyf0zb.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-11-tyf0zb.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-11-tyf0zb.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-11-tyf0zb.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-12-1ms1i1.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-12-1ms1i1.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-12-1ms1i1.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-12-1ms1i1.webm`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-9-1w9c77.filmstrip.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-9-1w9c77.out`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-9-1w9c77.png`
- `demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-6-WI-9-1w9c77.webm`
- `demo/INIT-2026-10-11-i3b-self-service/DEMO.md`
- `demo/INIT-2026-10-11-i3b-self-service/demo-plan.json`
- `demo/INIT-2026-10-11-i3b-self-service/demo.json`
- `gitweave.egg-info/SOURCES.txt`
- `gitweave/auth.py`
- `gitweave/cli.py`
- `gitweave/config.py`
- `gitweave/managers/repos.py`
- `gitweave/managers/rulesets.py`
- `gitweave/managers/teams.py`
- `gitweave/plan.py`
- `gitweave/policy.py`
- `gitweave/reset.py`
- `gitweave/self_serve/__init__.py`
- `gitweave/self_serve/exceptions.py`
- `gitweave/self_serve/membership.py`
- `gitweave/self_serve/new_repo.py`
- `gitweave/self_serve/update_content.py`
- `pyproject.toml`
- `requirements.txt`
- `tests/acceptance/test_gw_apply_path.py`
- `tests/acceptance/test_gw_containment.py`
- `tests/acceptance/test_gw_reset_before_apply.py`
- `tests/acceptance/test_gw_reset_readback.py`
- `tests/acceptance/test_gw_self_serve.py`
- `tests/acceptance/test_gw_workflow.py`
- `tests/conftest.py`
- `tests/test_apply_reset.py`
- `tests/test_caller_auth.py`
- `tests/test_cli_check_permission.py`
- `tests/test_cli_policy_error.py`
- `tests/test_cli_remove_member.py`
- `tests/test_cli_self_serve.py`
- `tests/test_config.py`
- `tests/test_gw_teams.py`
- `tests/test_manager_resources.py`
- `tests/test_ownership_marker.py`
- `tests/test_plan_self_serve.py`
- `tests/test_policy.py`
- `tests/test_policy_fail_closed.py`
- `tests/test_policy_jsonschema_required.py`
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

- `gw plan` — Plan output gains self-serve resource types with all three action branches (unchanged)
- `python3 -m pytest tests/` — Full offline test suite passes with 0 failures (changed)

```
- collected 577 items
+ collected 694 items
- tests/acceptance/test_gw_apply_path.py Fs                                [  0%]
+ tests/acceptance/test_gw_apply_path.py .                                 [  0%]
- tests/acceptance/test_gw_reset_before_apply.py ..                        [  0%]
+ tests/acceptance/test_gw_containment.py .                                [  0%]
- tests/acceptance/test_gw_workflow.py ..
+ tests/acceptance/test_gw_reset_before_apply.py ..                        [  0%]
+ tests/acceptance/test_gw_reset_readback.py 
```
- `python3 -m pytest tests/test_rulesets_unsupported_plan.py` — Rulesets unsupported-plan typed check passes (changed)

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
- `python3 -m pytest tests/acceptance/test_gw_reset_readback.py` — Reset proven by API read-back after a real create (changed)

```
- collected 0 items
+ collected 1 item
- ============================ no tests ran in <duration> =============================
+ tests/acceptance/test_gw_reset_readback.py .                             [100%]
- [stderr] ERROR: file or directory not found: tests/acceptance/test_gw_reset_readback.py
+ 
+ ============================== 1 passed in <duration> ==============================
+ 
```
- `python3 -m pytest tests/acceptance/test_gw_containment.py` — Containment proven by API state after apply and reset (changed)

```
- collected 0 items
+ collected 1 item
- ============================ no tests ran in <duration> =============================
+ tests/acceptance/test_gw_containment.py .                                [100%]
- [stderr] ERROR: file or directory not found: tests/acceptance/test_gw_containment.py
+ 
+ ============================== 1 passed in <duration> ==============================
+ 
```

4 of 5 checkpoints changed behaviour. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._

---

## Demo

▶ **[Open the rendered demo: `demo/INIT-2026-10-11-i3b-self-service/DEMO.md`](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/DEMO.md)** — renders inline on GitHub (works for private repos too).

The screenshots are also visible in this PR's **Files changed** tab (committed under `demo/INIT-2026-10-11-i3b-self-service/`).

Demo artefacts:
- [`DEMO.md`](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/DEMO.md)
- [`demo-plan.json`](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/demo-plan.json)
- [`demo.json`](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/demo.json)


### Captured checkpoints

**Plan-1-WI-8-1yki11**

![Plan-1-WI-8-1yki11 — before](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.filmstrip.png?raw=true)

![Plan-1-WI-8-1yki11 — after](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.filmstrip.png?raw=true)

[▶ Plan-1-WI-8-1yki11 — before (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-1-WI-8-1yki11.webm)

[▶ Plan-1-WI-8-1yki11 — after (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-1-WI-8-1yki11.webm)

**Plan-2-WI-10-einnrt**

![Plan-2-WI-10-einnrt — before](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.filmstrip.png?raw=true)

![Plan-2-WI-10-einnrt — after](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.filmstrip.png?raw=true)

[▶ Plan-2-WI-10-einnrt — before (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-2-WI-10-einnrt.webm)

[▶ Plan-2-WI-10-einnrt — after (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-2-WI-10-einnrt.webm)

**Plan-3-WI-13-17ca4u**

![Plan-3-WI-13-17ca4u — before](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.filmstrip.png?raw=true)

![Plan-3-WI-13-17ca4u — after](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.filmstrip.png?raw=true)

[▶ Plan-3-WI-13-17ca4u — before (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-3-WI-13-17ca4u.webm)

[▶ Plan-3-WI-13-17ca4u — after (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-3-WI-13-17ca4u.webm)

**Plan-4-WI-11-14sjx4**

![Plan-4-WI-11-14sjx4 — before](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.filmstrip.png?raw=true)

![Plan-4-WI-11-14sjx4 — after](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.filmstrip.png?raw=true)

[▶ Plan-4-WI-11-14sjx4 — before (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-4-WI-11-14sjx4.webm)

[▶ Plan-4-WI-11-14sjx4 — after (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-4-WI-11-14sjx4.webm)

**Plan-5-WI-12-tyf0zc**

![Plan-5-WI-12-tyf0zc — before](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.filmstrip.png?raw=true)

![Plan-5-WI-12-tyf0zc — after](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.filmstrip.png?raw=true)

[▶ Plan-5-WI-12-tyf0zc — before (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/before/Plan-5-WI-12-tyf0zc.webm)

[▶ Plan-5-WI-12-tyf0zc — after (webm)](https://github.com/parsoFish/GitWeave/blob/97ac77f01c0182b368e7d13f4044a1e71a00792a/demo/INIT-2026-10-11-i3b-self-service/.capture/after/Plan-5-WI-12-tyf0zc.webm)

