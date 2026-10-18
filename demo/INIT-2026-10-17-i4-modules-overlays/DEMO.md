# I4 — Modules that exist, and overlays that apply them

> _Derived from `demo.json` (D-07). Essence:_ I4 — Modules that exist, and overlays that apply them — 19 work items delivered against 111 acceptance criteria, 2 merge-boundary gates run.

## What this enables

_Agent narrative — not evidence._

Operators can now declare Copier modules in repo overlay configs; gw apply renders and commits them atomically to every matching branch via the Git Trees API — no pull requests, no partial states. gw plan previews the overlay diff offline before anything is committed. Teams request permitted modules through policy-gated self-service, and the recording transport makes the no-PR contract machine-checkable across every code path.

## Summary

- WI-1 [complete] # WI-1: Ground hygiene — egg-info .gitignore + rulesets 403 split
- WI-2a [complete] # WI-2a: Copier modules — python_service module + dependency + config
- WI-2b [complete] # WI-2b: Copier modules — terraform_module
- WI-3 [complete] # WI-3: gw module render CLI subcommand + min_copier_version enforcement
- WI-4 [complete] # WI-4: Recording transport + no-PR invariant (I3b residual #7)
- WI-5 [complete] # WI-5: Overlay schema spec.modules + policy schema allowed_modules
- WI-6 [complete] # WI-6: Overlay apply engine — Git Trees API, 3 state branches
- WI-7 [complete] # WI-7: gw overlay status — read .copier-answers.yml via API
- WI-8 [complete] # WI-8: gw plan overlay-aware + retire scripts/apply-overlays.py
- WI-9 [complete] # WI-9: gw overlay request — self-service + policy enforcement
- WI-10 [complete] # WI-10: I3b residuals #1-6
- WI-11 [complete] # WI-11: Live acceptance tests — overlay apply/status/request
- WI-12 [complete] # WI-12: Integration — all-tests-green
- WI-13 [complete] K1 — Answers-file contract: one record per module at .gitweave/<module>.copier-answers.yml (operator item 1 + item 9 regression). The round-2 plan's single root .copier-answers.yml lets a second module overwrite the first's record; gw apply, gw overlay status and self-serve request all read and write the per-module path, which is I5's merge base. The plan's WI-6/WI-7/WI-8/WI-11 build a single root .copier-answers.yml; K1 migrates their code and tests to the per-module path.
- WI-14 [complete] K2 — Apply-path edges the round-2 plan deferred (operator items 2, 3, 4): an empty repository (no commits) bootstraps and receives the modules (the demo's own path); gw overlay status on a repository with no modules prints 'no modules applied' and exits 0; a push refused by branch protection fails non-zero naming the repository, branch and protection, and never reports success.
- WI-15 [complete] K3 — terraform_module as team content (operator R69 option a) + module directories named by _metadata.name (items 5, 8). GitWeave itself stays Terraform-free: the docs guards scan GitWeave's own docs, README and copilot-context only, never modules/, and still bite on a Terraform token in GitWeave's own docs.
- WI-16 [complete] K4 — Copier as a declared dependency, version-enforced (items 6, 7): copier is declared in pyproject.toml's dependencies with the same spec as requirements.txt, and gw module render refuses a module whose min_copier_version is above the installed Copier, naming both versions (no deferral).
- WI-17 [failed] # WI-17 — review-fix concern (code-fix)
- WI-18 [complete] # WI-18 — review-fix concern (code-fix)
- Commit: `2682085c7b9e3ecc819688b748a72fe916d3e917`

## Visual Changes

### gw plan shows overlay diff — would add or unchanged per declared repo


### Primary quality gate green: structure, overlay schema and copier schema tests all pass


### gw apply commits rendered module files to repos atomically, no pull request opened


### git ls-files confirms no tracked files under gitweave.egg-info/ after gitignore entry added


## Test Evidence

| test | result | delta |
|---|---|---|
| local: python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero | pass | — |
| ci: python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py | pass | — |

> result: **pass**/**fail** · **skip** = not run in this gate (e.g. a live test with no credentials present) — not a failure · delta **new** = test added by this change.

## Acceptance criteria

- (WI-1) GIVEN the .gitignore file WHEN git ls-files gitweave.egg-info runs THEN it produces no output; git check-ignore gitweave.egg-info/SOURCES.txt exits zero
- (WI-1) GIVEN an org whose plan endpoint returns 403 with a rulesets-unsupported body WHEN gw plan --json runs THEN the rulesets field in JSON output is reported as unsupported with the API error message; exit 0
- (WI-1) GIVEN an org where the 403 indicates a missing token permission (not plan-lacking-rulesets) WHEN gw plan runs THEN gw plan exits non-zero and prints the name of the missing permission
- (WI-1) GIVEN the rulesets manager source code WHEN grep runs over gitweave/managers/rulesets.py THEN no line contains the string '403' inside str(exc) string matching; the two 403 cases are distinguished by response body content or exception type, not string coercion
- (WI-2a) GIVEN modules/python_service/copier.yaml WHEN jsonschema validates it against schemas/copier-module.schema.json THEN validates without errors; has a CalVer version, snake_case name matching directory, and at least one input that changes rendered output
- (WI-2a) GIVEN modules/python_service/.github/workflows/ci.yml.jinja WHEN the rendered CI workflow file is checked with yamllint THEN yamllint exits zero on the rendered output
- (WI-2a) GIVEN pyproject.toml WHEN grep runs for copier in dependencies THEN copier>=9.0 is listed in project.dependencies; requirements.txt pins the same version with a format-stability note comment
- (WI-2a) GIVEN config/repos/example.yaml WHEN it is parsed THEN it references python_service or terraform_module (not example-template); the CI smoke fixture continues to pass
- (WI-2b) GIVEN modules/python_service/copier.yaml and modules/terraform_module/copier.yaml WHEN jsonschema validates each against schemas/copier-module.schema.json THEN both validate without errors; each has a CalVer version, snake_case name matching its directory, and at least one input that changes rendered output
- (WI-2b) GIVEN each module's template directory WHEN the rendered CI workflow file is checked with yamllint THEN yamllint exits zero on the rendered output
- (WI-2b) GIVEN terraform_module has >=1 input declared WHEN test_terraform_module_has_input_that_changes_output runs THEN test passes
- (WI-3) GIVEN a module exists under modules/<name>/ with a valid copier.yaml WHEN gw module render <name> --dest <tmp> runs offline with one non-default input passed via --data key=value THEN the rendered tree under <tmp> contains the module's declared files; the non-default input value appears in the rendered output; exit 0
- (WI-3) GIVEN a module whose copier.yaml declares min_copier_version: '999.0.0' WHEN gw module render <name> --dest <tmp> runs THEN the command exits non-zero and prints a message naming both the required version and the installed version
- (WI-3) GIVEN gw module render produces a rendered CI workflow file WHEN yamllint is run on the rendered file THEN yamllint exits zero
- (WI-3) GIVEN the CLI parser WHEN gw module render --help is called THEN exit 0; the module group and render subcommand are registered in the argparse parser
- (WI-4) GIVEN code that uses RecordingTransport to intercept HTTP calls WHEN the overlay apply path runs (create branch) THEN the recording transport's request log contains zero entries matching POST /repos/*/pulls
- (WI-4) GIVEN a deliberate code mutant that calls POST /repos/{owner}/{repo}/pulls inside the overlay apply path WHEN the recording transport test runs THEN the assertion fails — proving the recording transport catches the violation
- (WI-4) GIVEN both the self-serve code path and the overlay apply code path WHEN they are invoked through the recording transport THEN both paths' HTTP calls are captured in the same request log
- (WI-4) GIVEN GW_CONTROL_REPO is referenced in the codebase WHEN grep runs over gitweave/ THEN no occurrences found; _assert_no_control_repo_pr and GW_CONTROL_REPO are removed
- (WI-5) GIVEN an overlay config with spec.modules: [{name: python_service, version: '2026.10.1', inputs: {service_name: foo}}] WHEN jsonschema validates it against schemas/overlay.schema.json THEN validation passes without errors
- (WI-5) GIVEN config/policy.yaml with per-team allowed_modules: [python_service] and a second team with allowed_modules: [terraform_module] WHEN PolicyLoader().load() runs THEN the loaded policy object exposes per-team allowed_modules; an invalid policy.yaml fails at load time with a schema error
- (WI-5) GIVEN config/policy.yaml is absent WHEN PolicyLoader().load() runs THEN raises a named PolicyError (not FileNotFoundError); the error message names the policy rule
- (WI-5) GIVEN schemas/policy.schema.json is a valid JSON Schema document WHEN jsonschema validates config/policy.yaml against it THEN validation passes
- (WI-6) GIVEN an overlay entry with spec.modules and a repo with no applied modules WHEN gw overlay apply <repo> runs through RecordingTransport THEN the transport log contains: create blob calls, create tree call, create commit call, update ref call; zero POST /repos/*/pulls calls; the rendered files are committed atomically to the default branch
- (WI-6) GIVEN the applied repository where .copier-answers.yml already matches the declared (name, version, inputs) triple WHEN gw overlay apply <repo> runs THEN no new commit is made; the transport log contains no blob/tree/commit/ref write calls
- (WI-6) GIVEN the applied repository where declared inputs differ from .copier-answers.yml (same version, different inputs) WHEN gw overlay apply <repo> runs THEN a new commit appears; .copier-answers.yml content in the commit reflects the new inputs; zero POST /repos/*/pulls
- (WI-6) GIVEN the CLI parser WHEN gw overlay apply --help is called THEN exit 0; the overlay group and apply subcommand are registered
- (WI-7) GIVEN a repository with a .copier-answers.yml recording one applied module WHEN gw overlay status <repo> runs THEN output prints the module's name, version, and inputs, sourced from the repository's .copier-answers.yml via API read-back; exit 0
- (WI-7) GIVEN a repository with no .copier-answers.yml WHEN gw overlay status <repo> runs THEN output prints an informative 'no modules applied' message; exit 0
- (WI-7) GIVEN the CLI parser WHEN gw overlay status --help is called THEN exit 0; the overlay status subcommand is registered
- (WI-8) GIVEN a recorded fixture containing one repo-without-modules entry and one repo-at-declared-version entry WHEN gw plan runs with all GW_* variables unset THEN output lists the module files to add for the repo-without-modules entry; produces no file-change output for the repo-at-declared-version entry; exit 0
- (WI-8) GIVEN scripts/apply-overlays.py exists WHEN git ls-files scripts/apply-overlays.py runs after this WI is delivered THEN the file is not tracked; it has been deleted
- (WI-8) GIVEN the CI dry-run-smoke job in .github/workflows/ WHEN it is inspected THEN it invokes gw plan (not apply-overlays.py); the job still runs credential-free
- (WI-8) GIVEN the offline fixture format WHEN it is documented in tests/test_plan_overlay.py module docstring or a comment THEN the format is described: what keys are present, how repos are represented, how applied-module state is recorded
- (WI-9) GIVEN config/policy.yaml declares python_service allowed for team-a, and team-a owns the target repo WHEN gw overlay request --team team-a --repo target-repo --module python_service runs via RecordingTransport THEN the module is applied with no pull request (transport.assert_no_pr_opens() passes); exit 0
- (WI-9) GIVEN config/policy.yaml declares terraform_module NOT in team-a's allowed_modules WHEN gw overlay request --team team-a --repo target-repo --module terraform_module runs THEN exits non-zero; prints the policy rule name; zero write-call records in the transport log after the refusal
- (WI-9) GIVEN config/policy.yaml is absent WHEN gw overlay request runs THEN exits non-zero with a named policy rule error (not FileNotFoundError); zero write calls
- (WI-9) GIVEN the CLI parser WHEN gw overlay request --help is called THEN exit 0; the overlay request subcommand is registered with --team, --repo, --module arguments
- (WI-10) GIVEN tests/test_cli_check_permission.py enumerates subcommands from the argparse parser WHEN it runs after I4 CLI wiring is complete THEN the test includes gw module render, gw overlay apply, gw overlay status, gw overlay request; a new subcommand without a permission check must fail the test
- (WI-10) GIVEN the add_membership / remove_membership endpoint text in acceptance tests WHEN tests asserting these endpoint names run THEN they pass with the current endpoint names; code is unchanged (documentation only)
- (WI-10) GIVEN the repo-scope idempotency test WHEN the command runs a second time THEN the test asserts zero write calls on the second run; the test also asserts the custom-property value written on the first run
- (WI-10) GIVEN gw self-serve list-exceptions WHEN called without --team THEN lists every team's exceptions; when called with --team, lists one team's exceptions; backward-compatible
- (WI-10) GIVEN the add-member live test WHEN it runs against the throwaway org THEN it starts from a verified absent membership, runs the command, reads membership back as present, then cleans up; a no-op command must fail this test
- (WI-10) GIVEN per-repo CLI tests for update-content, add-member, add-exception WHEN they run THEN they drive the real dispatch path; only the HTTP transport is faked (not entire function patched)
- (WI-10) GIVEN each of the 7 I3b residuals WHEN a no-op mutant of the behaviour is substituted THEN the residual's covering test fails
- (WI-11) GIVEN an overlay entry for a throwaway-org repository that has no applied modules WHEN gw overlay apply runs live (GW_* set) THEN the default branch holds the rendered module files and a .copier-answers.yml (verified via GET /repos/{owner}/{repo}/contents/.copier-answers.yml); transport log contains zero POST /repos/*/pulls; no pull request exists
- (WI-11) GIVEN the applied repository from AC above with the same version and inputs in its overlay entry WHEN gw overlay apply runs live a second time THEN the default-branch HEAD SHA is unchanged (verified via GET /repos/{owner}/{repo})
- (WI-11) GIVEN the applied repository where the overlay entry now specifies different inputs at the same CalVer version WHEN gw overlay apply runs live THEN a new commit appears on the default branch; .copier-answers.yml reflects the new inputs (verified via GET); transport log contains zero POST /repos/*/pulls
- (WI-11) GIVEN the applied repository from AC above WHEN gw overlay status <repo> runs live THEN output prints the module's name, version and inputs sourced from .copier-answers.yml via API read-back
- (WI-11) GIVEN config/policy.yaml declares module M allowed and module N not allowed for a team, and the team owns the target repository WHEN the team requests M via gw overlay request live THEN M is applied with no pull request (transport log confirms zero POST /repos/*/pulls); N is refused with the policy rule name; zero write-call records after the refusal
- (WI-12) GIVEN all GW_* environment variables are unset WHEN python3 -m pytest tests/ (excluding acceptance) runs THEN zero test failures; the full credential-free suite is green
- (WI-12) GIVEN the recording transport test runs across both self-serve and overlay paths WHEN every recorded HTTP request is inspected THEN no request is POST /repos/*/pulls; a deliberate code mutant that opens a pull request causes this assertion to fail
- (WI-12) GIVEN all I4 deliverables are on the branch WHEN python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero runs THEN zero failures (the project's primary quality gate is green)
- (WI-13) GIVEN a repository on the recording transport with python_service already applied WHEN gw apply applies terraform_module to the same repository THEN the committed tree holds .gitweave/python_service.copier-answers.yml and .gitweave/terraform_module.copier-answers.yml, no root .copier-answers.yml, and python_service's record is byte-identical to before
- (WI-13) GIVEN a mutant that writes every module's answers to the root .copier-answers.yml WHEN the per-module test runs against the mutant inside the suite (the test's name contains 'root_answers_file_mutant') THEN the mutant run fails the per-module assertion (regression guard for the one-root-file design)
- (WI-13) GIVEN a prefixed throwaway-org repository and an overlay entry listing python_service and terraform_module WHEN gw apply runs live, then gw overlay status <repo> THEN GET contents returns both .gitweave/<module>.copier-answers.yml files and status lists both modules with name, version and inputs; the repository is deleted afterwards
- (WI-14) GIVEN a newly created prefixed throwaway-org repository with no commits WHEN gw apply runs live with an overlay entry for it THEN GET contents on the default branch returns the module's rendered files and its answers file; the repository is deleted afterwards
- (WI-14) GIVEN the recording transport answers the ref lookup with 409 'Git Repository is empty' WHEN gw apply runs, and again with the bootstrap step mutated to a no-op THEN the real run commits the tree; the mutant run fails the test's assertion
- (WI-14) GIVEN a repository with no .gitweave/ directory (contents API 404) WHEN gw overlay status <repo> runs THEN it prints 'no modules applied' and exits 0 with no traceback
- (WI-14) GIVEN the recording transport refuses the ref update with a branch-protection error WHEN gw apply runs THEN it exits non-zero, names the repository, the branch and the protection, and prints no success line for that module
- (WI-15) GIVEN the modules/ tree WHEN each module directory's copier.yaml is read THEN python_service and terraform_module both exist, and every directory name equals its copier.yaml _metadata.name
- (WI-15) GIVEN the narrowed Terraform docs guards WHEN the guard suite runs, including a test that plants a Terraform token in a temporary copy of GitWeave's own docs and one that plants it under modules/ (test names contain 'bite' for the planted-docs case and 'modules' for the modules/ case) THEN the guard flags the planted docs token, ignores modules/, and the real tree passes
- (WI-15) GIVEN terraform_module WHEN gw module render terraform_module --dest <tmp> runs offline with a non-default module_name THEN the rendered main.tf and CI workflow contain that module_name and the CI workflow parses as YAML
- (WI-16) GIVEN pyproject.toml and requirements.txt WHEN their copier entries are compared THEN both declare copier with the same version specifier
- (WI-16) GIVEN a test module whose copier.yaml declares min_copier_version above the installed Copier WHEN gw module render runs on it, and again with the enforcement mutated to a no-op THEN the real run exits non-zero naming the required and installed versions and renders nothing; the mutant run fails the test
- (WI-17) GIVEN the gitweave package and its tests WHEN any file is searched for GW_TOKEN THEN no file references GW_TOKEN: live overlay auth uses the GitHub App installation token (auth.get_installation_token), and tests never inject a token env var
- (WI-17) GIVEN GW_TOKEN is unset and HTTP is intercepted WHEN gw overlay apply <repo> runs through the real CLI dispatch THEN auth.get_installation_token is called and every overlay HTTP request carries its token in Authorization (spy probe, no injected env)
- (WI-17) GIVEN a repo config declaring spec.modules WHEN gitweave.apply.apply(org) runs (gw apply) THEN gw apply applies that repo's overlays through the overlay apply path (apply_overlays_for_repo or apply_module_to_repo is invoked for the repo)
- (WI-17) GIVEN live GW_* credentials and GW_TOKEN unset WHEN tests/acceptance/test_gw_apply_overlay_live.py runs: it creates a prefixed empty repo, declares an overlay for it in a temporary config, runs `gw apply` as a subprocess, then cleans up THEN the default branch holds the rendered .github/workflows/ci.yml and the module answers file, read back through the API with the installation token; a second `gw apply` leaves the head SHA unchanged; no pull request exists; 0 skipped
- (WI-17) GIVEN the recorded fixture and no credentials WHEN gw plan --json --fixture tests/fixtures/overlay-smoke.json runs THEN it exits 0 and prints JSON with a rulesets field and the overlay items
- (WI-17) GIVEN the org rulesets endpoint returns 403 {"message":"Resource not accessible by integration"} (missing token permission) WHEN RulesetsManager.list_managed runs THEN it raises (exit non-zero at the CLI, naming the permission) instead of returning an empty list; the plan-lacking body "Upgrade to GitHub Team to enable this feature." is the only 403 reported as unsupported
- (WI-17) GIVEN the live throwaway org, whose plan lacks rulesets WHEN gw plan --json runs live THEN exit 0 and the rulesets field reports "unsupported" carrying the API message ("Upgrade to GitHub Team…"), not [] or "no drift"
- (WI-17) GIVEN the gitweave package WHEN HTTP errors are classified THEN no code path classifies by status-code substring ("403" in str(exc)/msg anywhere; any "<3 digits>" in in overlays.py); classification uses exc.status / resp.status_code
- (WI-17) GIVEN a fixture repo whose applied python_service version is 19990101.0 (older than declared) WHEN gw plan runs offline THEN the overlay line reports an update, not "unchanged"
- (WI-17) GIVEN team a with allowed_modules [python_service] and allowed_repo_patterns [a-*] WHEN team a requests python_service for repo b-x THEN the request is refused naming allowed_repo_patterns and apply is never called
- (WI-17) GIVEN the repository WHEN tests and code are searched THEN GW_CONTROL_REPO and _assert_no_control_repo_pr are gone
- (WI-17) GIVEN a mutant where apply_module_to_repo also POSTs /repos/{r}/pulls WHEN the overlay and self-serve unit suites run THEN at least one test fails: the no-PR assertion runs on the REAL self-serve request path (apply_module_to_repo is not patched out in those tests)
- (WI-17) GIVEN a mutant that writes "wrong-value" as the repo-scope custom property value WHEN the offline suite runs THEN at least one offline test fails that passes on the unmutated tree (the repo-scope idempotency test asserts the value actually written, not a hardcoded fake GET)
- (WI-17) GIVEN the self-serve CLI WHEN tests/test_cli_self_serve_real_dispatch.py runs THEN add-member and add-exception (as well as update-content) each have a real-parser/real-dispatch test, only HTTP faked, asserting the write request each makes (method, path and body); a handler that skips its write fails it
- (WI-17) GIVEN live GW_* credentials WHEN the live add-member test runs with gw self-serve add-member made a no-op in the subprocess (sitecustomize mutant) THEN the test fails: it asserts the membership absent first without pre-adding it, runs the command, reads it back present, and cleans up in tearDown
- (WI-17) GIVEN an empty repository and a module rendering several files WHEN the overlay is applied THEN the module answers file is written last, so a failure part-way never records the module as applied (asserted on the recorded request order in tests/test_overlay_empty_repo.py)
- (WI-17) GIVEN a transport whose every response is None (ref 404) WHEN apply_module_to_repo runs THEN it raises a named error, not TypeError
- (WI-17) GIVEN the empty-repo and two-module live acceptance tests WHEN they are read THEN each reads back .github/workflows/ (a rendered module file) through the API and asserts its content, not only the commit SHA
- (WI-17) GIVEN modules/terraform_module rendered with a non-default input WHEN tests/test_module_terraform_render.py -k yamllint runs THEN the rendered CI workflow passes yamllint
- (WI-17) GIVEN all GW_* variables unset WHEN python3 -m pytest tests/ runs THEN zero failures: live tests skip with a reason naming GW_*, they never self.fail (AC12)
- (WI-18) GIVEN the gitweave package and its tests WHEN any file is searched for GW_TOKEN THEN no file references GW_TOKEN: live overlay auth uses the GitHub App installation token (auth.get_installation_token), and tests never inject a token env var
- (WI-18) GIVEN GW_TOKEN is unset and HTTP is intercepted WHEN gw overlay apply <repo> runs through the real CLI dispatch THEN auth.get_installation_token is called and every overlay HTTP request carries its token in Authorization (spy probe, no injected env)
- (WI-18) GIVEN a repo config declaring spec.modules WHEN gitweave.apply.apply(org) runs (gw apply) THEN gw apply applies that repo's overlays through the overlay apply path (apply_overlays_for_repo or apply_module_to_repo is invoked for the repo)
- (WI-18) GIVEN live GW_* credentials and GW_TOKEN unset WHEN tests/acceptance/test_gw_apply_overlay_live.py runs: it creates a prefixed empty repo, declares an overlay for it in a temporary config, runs `gw apply` as a subprocess, then cleans up THEN the default branch holds the rendered .github/workflows/ci.yml and the module answers file, read back through the API with the installation token; a second `gw apply` leaves the head SHA unchanged; no pull request exists; 0 skipped
- (WI-18) GIVEN the recorded fixture and no credentials WHEN gw plan --json --fixture tests/fixtures/overlay-smoke.json runs THEN it exits 0 and prints JSON with a rulesets field and the overlay items
- (WI-18) GIVEN the org rulesets endpoint returns 403 {"message":"Resource not accessible by integration"} (missing token permission) WHEN RulesetsManager.list_managed runs THEN it raises (exit non-zero at the CLI, naming the permission) instead of returning an empty list; the plan-lacking body "Upgrade to GitHub Team to enable this feature." is the only 403 reported as unsupported
- (WI-18) GIVEN the live throwaway org, whose plan lacks rulesets WHEN gw plan --json runs live THEN exit 0 and the rulesets field reports "unsupported" carrying the API message ("Upgrade to GitHub Team…"), not [] or "no drift"
- (WI-18) GIVEN the gitweave package WHEN HTTP errors are classified THEN no code path classifies by status-code substring ("403" in str(exc)/msg anywhere; any "<3 digits>" in in overlays.py); classification uses exc.status / resp.status_code
- (WI-18) GIVEN a fixture repo whose applied python_service version is 19990101.0 (older than declared) WHEN gw plan runs offline THEN the overlay line reports an update, not "unchanged"
- (WI-18) GIVEN team a with allowed_modules [python_service] and allowed_repo_patterns [a-*] WHEN team a requests python_service for repo b-x THEN the request is refused naming allowed_repo_patterns and apply is never called
- (WI-18) GIVEN the repository WHEN tests and code are searched THEN GW_CONTROL_REPO and _assert_no_control_repo_pr are gone
- (WI-18) GIVEN a mutant where apply_module_to_repo also POSTs /repos/{r}/pulls WHEN the overlay and self-serve unit suites run THEN at least one test fails: the no-PR assertion runs on the REAL self-serve request path (apply_module_to_repo is not patched out in those tests)
- (WI-18) GIVEN a mutant that writes "wrong-value" as the repo-scope custom property value WHEN the offline suite runs THEN at least one offline test fails that passes on the unmutated tree (the repo-scope idempotency test asserts the value actually written, not a hardcoded fake GET)
- (WI-18) GIVEN the self-serve CLI WHEN tests/test_cli_self_serve_real_dispatch.py runs THEN add-member and add-exception (as well as update-content) each have a real-parser/real-dispatch test, only HTTP faked, asserting the write request each makes (method, path and body); a handler that skips its write fails it
- (WI-18) GIVEN live GW_* credentials WHEN the live add-member test runs with gw self-serve add-member made a no-op in the subprocess (sitecustomize mutant) THEN the test fails: it asserts the membership absent first without pre-adding it, runs the command, reads it back present, and cleans up in tearDown
- (WI-18) GIVEN an empty repository and a module rendering several files WHEN the overlay is applied THEN the module answers file is written last, so a failure part-way never records the module as applied (asserted on the recorded request order in tests/test_overlay_empty_repo.py)
- (WI-18) GIVEN a transport whose every response is None (ref 404) WHEN apply_module_to_repo runs THEN it raises a named error, not TypeError
- (WI-18) GIVEN the empty-repo and two-module live acceptance tests WHEN they are read THEN each reads back .github/workflows/ (a rendered module file) through the API and asserts its content, not only the commit SHA
- (WI-18) GIVEN modules/terraform_module rendered with a non-default input WHEN tests/test_module_terraform_render.py -k yamllint runs THEN the rendered CI workflow passes yamllint
- (WI-18) GIVEN all GW_* variables unset WHEN python3 -m pytest tests/ runs THEN zero failures: live tests skip with a reason naming GW_*, they never self.fail (AC12)
- (WI-18) GIVEN three source mutants of cmd_overlay_status in gitweave/cli.py, one at a time: the "No modules applied." print, the "  {name} @ {version}" line, and the "    {k}: {v}" inputs line each blanked WHEN the offline suite runs per mutant THEN each mutant fails at least one test: the overlay-status CLI handler is driven through dispatch with only HTTP faked, asserting the no-modules message, the module name@version line and each input line (keep those three print literals)
- (WI-18) GIVEN gitweave/managers/overlays.py and gitweave/self_serve/exceptions.py WHEN error handling is searched THEN no error is classified by message substring (no "<text>" in msg / str(exc) / err / .lower(): the empty-repo case uses the 409 status, the property-exists case uses the 422 status)
- (WI-18) GIVEN _get_repo_property in gitweave/self_serve/exceptions.py WHEN the properties GET returns data, 404, 403 or 500 THEN data gives the value and 404 gives None; 403 and 500 raise GithubException instead of returning None (no write on a failed read)
- (WI-18) GIVEN a fixture repo declaring python_service whose applied overlay is terraform_module at the current version WHEN gw plan runs offline THEN the overlay line reports drift or an update for the module mismatch, never "unchanged"
- (WI-18) GIVEN a stub scripts/apply-overlays.py restored in a copy of the tree WHEN the offline suite runs THEN at least one test fails: the retired script is asserted absent; the two tests in tests/test_dry_run_smoke.py that run the missing script and pass vacuously are replaced by that assertion
- (WI-18) GIVEN every module under modules/ WHEN template paths are scanned for {{ var }} THEN every variable used in a template path is a declared question in that module's copier.yaml (python_service uses repo_name undeclared, so rendering silently drops the directory)

## Files Changed

- `.github/workflows/ci.yaml`
- `.gitignore`
- `config/policy.yaml`
- `config/repos/example.yaml`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-1-WI-8-1yki11.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-1-WI-8-1yki11.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-1-WI-8-1yki11.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-1-WI-8-1yki11.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-2-WI-12-einnrv.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-2-WI-12-einnrv.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-2-WI-12-einnrv.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-2-WI-12-einnrv.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-3-WI-6-sw6ji5.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-3-WI-6-sw6ji5.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-3-WI-6-sw6ji5.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-3-WI-6-sw6ji5.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-4-WI-1-17kktq.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-4-WI-1-17kktq.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-4-WI-1-17kktq.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/after/Plan-4-WI-1-17kktq.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-1-WI-8-1yki11.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-1-WI-8-1yki11.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-1-WI-8-1yki11.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-1-WI-8-1yki11.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-2-WI-12-einnrv.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-2-WI-12-einnrv.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-2-WI-12-einnrv.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-2-WI-12-einnrv.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-3-WI-6-sw6ji5.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-3-WI-6-sw6ji5.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-3-WI-6-sw6ji5.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-3-WI-6-sw6ji5.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-4-WI-1-17kktq.filmstrip.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-4-WI-1-17kktq.out`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-4-WI-1-17kktq.png`
- `demo/INIT-2026-10-17-i4-modules-overlays/.capture/before/Plan-4-WI-1-17kktq.webm`
- `demo/INIT-2026-10-17-i4-modules-overlays/DEMO.md`
- `demo/INIT-2026-10-17-i4-modules-overlays/demo-plan.json`
- `demo/INIT-2026-10-17-i4-modules-overlays/demo.json`
- `gitweave.egg-info/PKG-INFO`
- `gitweave.egg-info/SOURCES.txt`
- `gitweave.egg-info/dependency_links.txt`
- `gitweave.egg-info/entry_points.txt`
- `gitweave.egg-info/requires.txt`
- `gitweave.egg-info/top_level.txt`
- `gitweave/apply.py`
- `gitweave/auth.py`
- `gitweave/cli.py`
- `gitweave/config.py`
- `gitweave/managers/overlays.py`
- `gitweave/managers/rulesets.py`
- `gitweave/module_render.py`
- `gitweave/plan.py`
- `gitweave/policy.py`
- `gitweave/reset.py`
- `gitweave/self_serve/exceptions.py`
- `gitweave/self_serve/membership.py`
- `gitweave/self_serve/overlay_request.py`
- `gitweave/transport.py`
- `modules/python_service/.github/workflows/ci.yml.jinja`
- `modules/python_service/copier.yaml`
- `modules/python_service/{{ repo_name }}/.gitkeep`
- `modules/terraform_module/.github/workflows/ci.yml.jinja`
- `modules/terraform_module/copier.yaml`
- `modules/terraform_module/terraform/main.tf.jinja`
- `pyproject.toml`
- `requirements.txt`
- `schemas/policy.schema.json`
- `scripts/apply-overlays.py`
- `tests/acceptance/test_gw_apply_overlay_live.py`
- `tests/acceptance/test_gw_apply_path.py`
- `tests/acceptance/test_gw_containment.py`
- `tests/acceptance/test_gw_overlay.py`
- `tests/acceptance/test_gw_overlay_empty_repo.py`
- `tests/acceptance/test_gw_overlay_two_modules.py`
- `tests/acceptance/test_gw_reset_before_apply.py`
- `tests/acceptance/test_gw_reset_readback.py`
- `tests/acceptance/test_gw_self_serve.py`
- `tests/acceptance/test_gw_workflow.py`
- `tests/fixtures/min_ver_fixture/copier.yaml`
- `tests/fixtures/overlay-smoke.json`
- `tests/test_cli_self_serve_real_dispatch.py`
- `tests/test_config.py`
- `tests/test_copier_modules.py`
- `tests/test_docs_no_terraform_tokens.py`
- `tests/test_dry_run_ci_workflow.py`
- `tests/test_dry_run_smoke.py`
- `tests/test_i3b_residuals.py`
- `tests/test_i4_integration.py`
- `tests/test_manager_resources.py`
- `tests/test_module_min_copier_version.py`
- `tests/test_module_render.py`
- `tests/test_module_terraform_render.py`
- `tests/test_overlay_answers_file_per_module.py`
- `tests/test_overlay_apply.py`
- `tests/test_overlay_empty_repo.py`
- `tests/test_overlay_protected_branch.py`
- `tests/test_overlay_request.py`
- `tests/test_overlay_status.py`
- `tests/test_overlay_status_empty.py`
- `tests/test_plan.py`
- `tests/test_plan_overlay.py`
- `tests/test_policy_overlay.py`
- `tests/test_recording_transport.py`
- `tests/test_rulesets_unsupported_plan.py`
- `tests/test_self_serve_exceptions.py`
- `tests/test_self_serve_membership.py`
- `tests/test_structure.py`

```
108 files changed, 7589 insertions(+), 611 deletions(-)
```
