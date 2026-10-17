---
work_item_id: WI-6
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on:
  - WI-2
  - WI-3
  - WI-4
  - WI-5
domain: overlay
acceptance_criteria:
  - given: "an overlay entry with spec.modules and a repo with no applied modules"
    when: "gw overlay apply <repo> runs through RecordingTransport"
    then: "the transport log contains: create blob calls, create tree call, create commit call, update ref call; zero POST /repos/*/pulls calls; the rendered files are committed atomically to the default branch"
  - given: "the applied repository where .copier-answers.yml already matches the declared (name, version, inputs) triple"
    when: "gw overlay apply <repo> runs"
    then: "no new commit is made; the transport log contains no blob/tree/commit/ref write calls"
  - given: "the applied repository where declared inputs differ from .copier-answers.yml (same version, different inputs)"
    when: "gw overlay apply <repo> runs"
    then: "a new commit appears; .copier-answers.yml content in the commit reflects the new inputs; zero POST /repos/*/pulls"
  - given: "the CLI parser"
    when: "gw overlay apply --help is called"
    then: "exit 0; the overlay group and apply subcommand are registered"
files_in_scope:
  - gitweave/managers/overlays.py
  - gitweave/cli.py
  - tests/test_overlay_apply.py
creates:
  - gitweave/managers/overlays.py
  - tests/test_overlay_apply.py
estimated_iterations: 5
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_overlay_apply.py::TestOverlayApply::test_create_branch_commits_rendered_files"
  - "-p"
  - "no:cacheprovider"
---

# WI-6: Overlay apply engine — Git Trees API, 3 state branches

Target: `gitweave/managers/overlays.py` (new), `gitweave/cli.py` (add `overlay` group), `tests/test_overlay_apply.py` (new).

## Y-statement

Git Trees API over Contents API: atomic tree → commit → ref update. Per manifest decision — **do not use Contents API per-file approach**.

## gitweave/managers/overlays.py

### Core data structures

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class ModuleSpec:
    name: str
    version: str
    inputs: dict[str, Any]


@dataclass  
class OverlayApplyResult:
    repo: str
    action: str   # "created" | "updated" | "unchanged"
    message: str
```

### Applied-state source of truth

Applied state is read ONLY from the repository's `.copier-answers.yml` via API GET. Never from a local cache.

```python
def _read_applied_state(gh_repo, module_name: str) -> dict | None:
    """GET /repos/{owner}/{repo}/contents/.copier-answers.yml.
    
    Returns parsed YAML dict or None if file not found.
    """
    ...
```

### Idempotency check

Compare the full `(name, version, inputs)` triple — NOT version alone:

```python
def _is_unchanged(declared: ModuleSpec, applied: dict) -> bool:
    return (
        applied.get("_module_name") == declared.name
        and applied.get("_module_version") == declared.version
        and applied.get("_answers", {}) == declared.inputs
    )
```

### Three state branches

```python
def apply_module_to_repo(
    gh_repo,  # PyGitHub Repository object
    module_spec: ModuleSpec,
    transport: RecordingTransport | None = None,
) -> OverlayApplyResult:
    """Apply a single module to a repo via Git Trees API.
    
    Branch 1 (create): applied_state is None → render, create blobs, create tree,
                        create commit, update ref. Include .copier-answers.yml.
    Branch 2 (unchanged): applied_state matches declared triple → return unchanged.
    Branch 3 (update): applied_state exists but differs → re-render, same API sequence.
    """
```

### Git Trees API sequence

For create and update branches:
1. `render_module(name, dest=tmp_dir, data=inputs)` — offline render
2. For each file in rendered tree: `POST /repos/{owner}/{repo}/git/blobs` → sha
3. `POST /repos/{owner}/{repo}/git/trees` with parent_tree + file blobs
4. `POST /repos/{owner}/{repo}/git/commits` with parent commit + tree
5. `PATCH /repos/{owner}/{repo}/git/refs/heads/{default_branch}` → update ref

**Never call `POST /repos/{owner}/{repo}/pulls`.** The recording transport in tests MUST verify this via `transport.assert_no_pr_opens()`.

### .copier-answers.yml format

Written as YAML to the rendered tree root before blobs are created:

```yaml
_module_name: python_service
_module_version: "2026.10.1"
_answers:
  service_name: my_service
  python_version: "3.11"
```

## CLI wiring: gitweave/cli.py

Import `apply_module_to_repo` and add the `overlay` subparser group:

```python
# overlay subcommands
p_ov = sub.add_parser("overlay", help="Module overlay operations")
ov_sub = p_ov.add_subparsers(dest="ov_command", required=True)

p_oa = ov_sub.add_parser("apply", help="Apply declared overlays for a repo")
p_oa.add_argument("repo", metavar="REPO", help="Repository name")
p_oa.set_defaults(func=cmd_overlay_apply)
```

```python
def cmd_overlay_apply(args):
    from gitweave.managers.overlays import apply_overlays_for_repo
    try:
        gh_org = _get_org_client()
        results = apply_overlays_for_repo(args.repo, gh_org)
        for r in results:
            print(f"  {r.action}: {r.repo} — {r.message}")
        sys.exit(0)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

## tests/test_overlay_apply.py

Use `RecordingTransport` from `gitweave.transport`. Fake the GitHub API responses — do NOT use real credentials. Tests must NOT inherit any GW_* autouse fixture.

Class `TestOverlayApply`:
- `test_create_branch_commits_rendered_files` — no applied state; asserts blob+tree+commit+ref calls; `transport.assert_no_pr_opens()`
- `test_unchanged_branch_no_write_calls` — applied state matches; asserts zero write calls
- `test_update_branch_commits_new_inputs` — applied state differs; asserts write calls; new .copier-answers.yml content
- `test_apply_help_exits_zero` — `gw overlay apply --help` exits 0

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
