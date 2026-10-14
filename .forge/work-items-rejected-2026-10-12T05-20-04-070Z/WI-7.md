---
work_item_id: WI-7
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-3
  - WI-4
  - WI-5
  - WI-6
acceptance_criteria:
  - given: "gw self-serve new-repo --team <slug> --name <name> is invoked via argparse"
    when: "main() parses and dispatches"
    then: "calls self_serve_new_repo with correct arguments and exits 0 on success"
  - given: "gw self-serve update-content --team <slug> --repo <name> --setting topics --value 'a,b' is invoked"
    when: "main() dispatches"
    then: "calls self_serve_update_content with correct arguments and exits 0"
  - given: "gw self-serve add-member --team <slug> --member <login> is invoked"
    when: "main() dispatches"
    then: "calls self_serve_add_member with correct arguments and exits 0"
  - given: "gw self-serve add-exception --team <slug> --repo <name> --exception <key> --reason <text>"
    when: "main() dispatches"
    then: "calls self_serve_add_exception and exits 0"
  - given: "gw self-serve list-exceptions --repo <name> is invoked"
    when: "main() dispatches"
    then: "calls self_serve_list_exceptions, prints JSON result, exits 0"
  - given: "any self-serve command and CallerTokenRequiredError is raised"
    when: "main() catches it"
    then: "prints error message to stderr containing 'caller-token-required' and exits non-zero"
  - given: "any self-serve command and PolicyDenied is raised"
    when: "main() catches it"
    then: "prints the policy denial message to stderr and exits non-zero"
files_in_scope:
  - gitweave/cli.py
  - tests/test_cli_self_serve.py
creates:
  - tests/test_cli_self_serve.py
verification_artifact: gitweave/cli.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_cli_self_serve.py::TestSelfServeCLI::test_new_repo_subcommand_registered"
  - "-p"
  - "no:cacheprovider"
domain: "cli"
---

# WI-7: CLI wiring — gw self-serve subcommands

Target: extend `gitweave/cli.py` with a `self-serve` subparser and its five subcommands.

## Argparse structure

```
gw self-serve new-repo --team SLUG --name NAME
gw self-serve update-content --team SLUG --repo REPO --setting TYPE --value VALUE
gw self-serve add-member --team SLUG --member LOGIN
gw self-serve remove-member --team SLUG --member LOGIN
gw self-serve add-exception --team SLUG --repo REPO --exception KEY --reason TEXT
gw self-serve list-exceptions --repo REPO [--json]
```

## Auth wiring

Each subcommand handler:
1. Calls `get_caller_token()` → token
2. Gets `get_github_client()` → App client
3. Calls `resolve_caller_login(token)` → caller_login
4. Calls `PolicyLoader().load()` → policy
5. Calls the appropriate self-serve function
6. On success: prints result, exits 0
7. On `PolicyDenied` or `CallerTokenRequiredError`: prints to stderr, exits 1

## Error-output contract

`CallerTokenRequiredError` → stderr message must contain `caller-token-required`.
`PolicyDenied` → stderr message must contain the policy rule name.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
