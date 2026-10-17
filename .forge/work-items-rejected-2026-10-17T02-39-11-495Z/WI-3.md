---
work_item_id: WI-3
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on:
  - WI-2
domain: modules
acceptance_criteria:
  - given: "a module exists under modules/<name>/ with a valid copier.yaml"
    when: "gw module render <name> --dest <tmp> runs offline with one non-default input passed via --data key=value"
    then: "the rendered tree under <tmp> contains the module's declared files; the non-default input value appears in the rendered output; exit 0"
  - given: "a module whose copier.yaml declares min_copier_version: '999.0.0'"
    when: "gw module render <name> --dest <tmp> runs"
    then: "the command exits non-zero and prints a message naming both the required version and the installed version"
  - given: "gw module render produces a rendered CI workflow file"
    when: "yamllint is run on the rendered file"
    then: "yamllint exits zero"
  - given: "the CLI parser"
    when: "gw module render --help is called"
    then: "exit 0; the module group and render subcommand are registered in the argparse parser"
files_in_scope:
  - gitweave/module_render.py
  - gitweave/cli.py
  - tests/test_module_render.py
creates:
  - gitweave/module_render.py
  - tests/test_module_render.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_module_render.py::TestModuleRender::test_render_non_default_input_appears_in_output"
  - "-p"
  - "no:cacheprovider"
---

# WI-3: gw module render CLI subcommand + min_copier_version enforcement

Target: `gitweave/module_render.py` (new), `gitweave/cli.py` (add `module` group), `tests/test_module_render.py` (new).

## Implementation: gitweave/module_render.py

```python
"""Offline module rendering via Copier."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class CopierVersionError(RuntimeError):
    """Installed Copier is older than module's min_copier_version."""


def _installed_copier_version() -> str:
    """Return installed Copier version string."""
    import copier
    return copier.__version__


def _check_version(module_path: Path) -> None:
    """Raise CopierVersionError if installed Copier < min_copier_version."""
    import yaml
    from packaging.version import Version
    copier_yaml = module_path / "copier.yaml"
    data = yaml.safe_load(copier_yaml.read_text())
    min_ver = data.get("_metadata", {}).get("min_copier_version")
    if min_ver is None:
        return
    installed = _installed_copier_version()
    if Version(installed) < Version(min_ver):
        raise CopierVersionError(
            f"Module requires copier>={min_ver}; installed={installed}"
        )


def render_module(name: str, dest: str, data: dict | None = None) -> None:
    """Render module <name> to <dest> offline.

    Args:
        name: snake_case module name (matches modules/<name>/ directory)
        dest: destination directory path (created if absent)
        data: optional dict of answers overriding copier defaults
    """
    modules_root = Path(__file__).parent.parent / "modules"
    module_path = modules_root / name
    if not module_path.is_dir():
        raise FileNotFoundError(f"Module not found: modules/{name}/")

    _check_version(module_path)

    import copier
    copier.run_copy(
        src_path=str(module_path),
        dst_path=dest,
        data=data or {},
        defaults=True,
        overwrite=True,
        vcs_ref=None,
    )
```

## CLI wiring: gitweave/cli.py

Add after the `self-serve` block but before `args = parser.parse_args()`:

```python
# module subcommands
p_mod = sub.add_parser("module", help="Copier module operations")
mod_sub = p_mod.add_subparsers(dest="mod_command", required=True)

p_mr = mod_sub.add_parser("render", help="Render a module offline to a destination")
p_mr.add_argument("name", metavar="NAME", help="Module name (snake_case)")
p_mr.add_argument("--dest", required=True, metavar="DIR", help="Destination directory")
p_mr.add_argument("--data", metavar="KEY=VALUE", nargs="*", default=[],
                  help="Override copier question answers (key=value pairs)")
p_mr.set_defaults(func=cmd_module_render)
```

Add `cmd_module_render` handler:

```python
def cmd_module_render(args):
    from gitweave.module_render import render_module, CopierVersionError
    data = {}
    for pair in (args.data or []):
        k, _, v = pair.partition("=")
        data[k.strip()] = v.strip()
    try:
        render_module(args.name, args.dest, data=data)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except CopierVersionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

## Test file: tests/test_module_render.py

Class `TestModuleRender` with:

- `test_render_non_default_input_appears_in_output` — renders `python_service` with a non-default `service_name`, asserts the value appears in at least one rendered file
- `test_min_copier_version_enforced` — patches `_installed_copier_version` to return `"0.0.1"`, asserts `CopierVersionError` raised
- `test_rendered_ci_workflow_passes_yamllint` — renders module, runs `yamllint` on the rendered workflow file, asserts exit 0
- `test_module_not_found_raises` — calls `render_module("nonexistent", ...)`, asserts `FileNotFoundError`
- `test_cli_module_render_help_exits_zero` — runs `gw module render --help` via subprocess, asserts exit 0

Tests must NOT inherit any GW_* autouse fixture (they run offline, no API calls).

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
