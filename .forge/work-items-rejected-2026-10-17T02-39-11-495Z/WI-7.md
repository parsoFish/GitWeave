---
work_item_id: WI-7
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on:
  - WI-6
domain: overlay
acceptance_criteria:
  - given: "a repository with a .copier-answers.yml recording one applied module"
    when: "gw overlay status <repo> runs"
    then: "output prints the module's name, version, and inputs, sourced from the repository's .copier-answers.yml via API read-back; exit 0"
  - given: "a repository with no .copier-answers.yml"
    when: "gw overlay status <repo> runs"
    then: "output prints an informative 'no modules applied' message; exit 0"
  - given: "the CLI parser"
    when: "gw overlay status --help is called"
    then: "exit 0; the overlay status subcommand is registered"
files_in_scope:
  - gitweave/managers/overlays.py
  - gitweave/cli.py
  - tests/test_overlay_status.py
creates:
  - tests/test_overlay_status.py
verification_artifact: gitweave/managers/overlays.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_overlay_status.py::TestOverlayStatus::test_status_prints_module_name_version_inputs"
  - "-p"
  - "no:cacheprovider"
---

# WI-7: gw overlay status — read .copier-answers.yml via API

Target: extend `gitweave/managers/overlays.py` with status reading; add overlay status subcommand to `gitweave/cli.py`; create `tests/test_overlay_status.py`.

## gitweave/managers/overlays.py extension

Add a `get_overlay_status(gh_repo) -> list[dict]` function:

```python
def get_overlay_status(gh_repo) -> list[dict]:
    """Read applied overlay state from .copier-answers.yml via API GET.
    
    Returns:
        List of dicts, one per applied module:
        [{"name": ..., "version": ..., "inputs": {...}}, ...]
        Empty list if no .copier-answers.yml found.
    """
    applied = _read_applied_state(gh_repo, module_name=None)  
    # or read the root .copier-answers.yml directly
    if applied is None:
        return []
    return [{
        "name": applied.get("_module_name"),
        "version": applied.get("_module_version"),
        "inputs": applied.get("_answers", {}),
    }]
```

Note: In I4 each repo has one `.copier-answers.yml` at root. I5 will handle multiple modules per repo. For now, return a single-element list (or empty).

## CLI wiring: gitweave/cli.py

Add `status` subcommand to the existing `overlay` subparser group (created in WI-6):

```python
p_os = ov_sub.add_parser("status", help="Show applied overlay modules for a repo")
p_os.add_argument("repo", metavar="REPO")
p_os.set_defaults(func=cmd_overlay_status)
```

```python
def cmd_overlay_status(args):
    from gitweave.managers.overlays import get_overlay_status
    try:
        gh_org = _get_org_client()
        gh_repo = gh_org.get_repo(args.repo)
        modules = get_overlay_status(gh_repo)
        if not modules:
            print("No modules applied.")
        else:
            for m in modules:
                print(f"  {m['name']} @ {m['version']}")
                for k, v in m.get("inputs", {}).items():
                    print(f"    {k}: {v}")
        sys.exit(0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

## tests/test_overlay_status.py

Use `unittest.mock.patch` to fake the GitHub API GET for `.copier-answers.yml`. No real credentials. Tests must NOT inherit any GW_* autouse fixture.

Class `TestOverlayStatus`:
- `test_status_prints_module_name_version_inputs` — patches the GET to return a YAML body with `_module_name`, `_module_version`, `_answers`; asserts printed output contains all three
- `test_status_no_answers_file_prints_none_applied` — patches GET to return 404; asserts "No modules applied" in output; exit 0
- `test_status_help_exits_zero` — `gw overlay status --help` exits 0

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
