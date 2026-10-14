---
work_item_id: WI-9
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-7
  - WI-8
acceptance_criteria:
  - given: "GW_CALLER_TOKEN set to an org-member token, team with new-repo permission in policy.yaml, name matches allowed pattern"
    when: "`gw self-serve new-repo --team <slug> --name <name>` runs against the throwaway org"
    then: "repo exists (verified via GET /repos/{org}/{name}), command exits 0, no PR opened on control repo"
  - given: "GW_CALLER_TOKEN set, team has content-update permission, requested setting in allowed set"
    when: "`gw self-serve update-content --team <slug> --repo <name> --setting topics --value forge,test` runs"
    then: "topics applied (verified via API read-back), exits 0, no PR opened on control repo"
  - given: "GW_CALLER_TOKEN set, requester is a team member per policy"
    when: "`gw self-serve add-member --team <slug> --member <login>` runs"
    then: "membership applied (verified via GET /orgs/{org}/teams/{slug}/memberships/{login}), exits 0, no PR opened"
  - given: "an allowed policy exception for a managed repository"
    when: "exception applied then `gw self-serve list-exceptions --repo <name>` runs"
    then: "exception listed (custom property verified via GET /repos/{org}/{repo}/properties/values)"
  - given: "a self-serve request that violates a named policy rule"
    when: "the self-serve command runs against the live org"
    then: "exits non-zero, output names the specific policy rule, org is unchanged"
  - given: "GW_CALLER_TOKEN is not set and gh auth token is unavailable"
    when: "any gw self-serve command runs"
    then: "exits non-zero with error containing 'caller-token-required'"
files_in_scope:
  - tests/acceptance/test_gw_self_serve.py
creates:
  - tests/acceptance/test_gw_self_serve.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/acceptance/test_gw_self_serve.py::TestSelfServeAcceptance::test_new_repo_within_policy"
  - "-p"
  - "no:cacheprovider"
domain: "self-serve"
---

# WI-9: Live acceptance tests — gw self-serve

Target: `tests/acceptance/test_gw_self_serve.py` — live tests against the throwaway org (`dave-parso`) with `FORGE_RESOURCE_PREFIX`-scoped resources.

## Environment requirements

Requires: `GW_ORG`, `GW_APP_ID`, `GW_APP_INSTALLATION_ID`, `GW_APP_PRIVATE_KEY_PATH`, `GW_CALLER_TOKEN`.
Skip all tests with `pytest.skip` when any is unset (the acceptance suite already follows this pattern in `tests/acceptance/`).

## Test scope (maps 1:1 to ACs)

1. `test_new_repo_within_policy` — creates a `{FORGE_RESOURCE_PREFIX}test-ss-repo` repo, asserts GET returns 200, cleanup deletes it.
2. `test_update_content_topics` — applies topics to an existing managed repo, asserts read-back.
3. `test_add_member_within_policy` — adds a test member to a team, asserts membership active, removes after.
4. `test_policy_exception_roundtrip` — adds exception + lists it, asserts property present.
5. `test_policy_violation_refused` — request that breaks a named rule → non-zero + rule name in output.
6. `test_missing_caller_token` — unsets GW_CALLER_TOKEN, asserts error contains 'caller-token-required'.

## Resource cleanup

Every test that writes a resource must clean it up in a `finally` block or `pytest.fixture` teardown. Resources use `FORGE_RESOURCE_PREFIX` so a stale cleanup doesn't harm the live org.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
