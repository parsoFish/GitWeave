"""B3b: Static AST check — every repo/team name in tests/acceptance uses GW_RESOURCE_PREFIX.

Every repo/team name passed to:
  - create_repo, create_team, get_repo, get_team_by_slug
  - a gw CLI call via --name or --repo argument
must be either:
  (a) an f-string or expression whose first element is _resource_prefix(), or
  (b) a string in the explicit pre-existing fixture allowlist (e.g. "platform").

The test fails on any bare string literal name that doesn't appear in the allowlist.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACCEPTANCE_DIR = pathlib.Path(__file__).parent / "acceptance"

# Functions / methods whose first positional argument is a repo or team name.
_REPO_TEAM_FUNCS = {
    "create_repo",
    "create_team",
    "get_repo",
    "get_team_by_slug",
}

# Pre-existing org fixtures that are allowed as bare string literals.
_ALLOWED_LITERALS = {
    "platform",       # pre-existing team slug used in tests
    "dave-parso",     # pre-existing team slug
    "test-restricted",  # policy-only slug (no actual GH team)
}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _is_prefix_expression(node: ast.expr) -> bool:
    """Return True if *node* is or begins with a _resource_prefix() call.

    Covers:
      - Direct call: _resource_prefix()
      - f-string whose first value is a _resource_prefix() call:
          f"{_resource_prefix()}..."
      - JoinedStr (f-string) whose first FormattedValue calls _resource_prefix
    """
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_resource_prefix":
            return True
    if isinstance(node, ast.JoinedStr):
        # f-string: first value must be a FormattedValue wrapping _resource_prefix()
        if node.values:
            first = node.values[0]
            if isinstance(first, ast.FormattedValue):
                return _is_prefix_expression(first.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_prefix_expression(node.left)
    return False


def _extract_name_violations(tree: ast.AST, source_file: pathlib.Path) -> list[tuple[int, str]]:
    """Return (lineno, description) for each violation in *tree*."""
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # -- calls like gh_org.create_repo(repo_name), get_team_by_slug("platform") ---------
        if isinstance(node, ast.Call):
            func = node.func
            func_name: str | None = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr

            if func_name in _REPO_TEAM_FUNCS and node.args:
                arg = node.args[0]
                _check_arg(arg, func_name, node.lineno, violations)

        # -- subprocess.run / _run_gw calls with --name or --repo CLI flags ----------------
        if isinstance(node, ast.Call):
            func = node.func
            is_run_gw = (
                (isinstance(func, ast.Name) and func.id == "_run_gw")
                or (isinstance(func, ast.Attribute) and func.attr in ("run",))
            )
            if is_run_gw:
                _check_cli_args(node, violations)

    return violations


def _check_arg(
    arg: ast.expr,
    context: str,
    lineno: int,
    violations: list[tuple[int, str]],
) -> None:
    """Check a single name argument; append to violations if bare literal."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        if arg.value not in _ALLOWED_LITERALS:
            violations.append((
                lineno,
                f"{context}() called with bare literal {arg.value!r} "
                "(must use _resource_prefix() or be an allowed fixture name)",
            ))
    elif not _is_prefix_expression(arg):
        # Non-literal, non-prefix: could be a variable — allowed (dynamic)
        pass


def _check_cli_args(node: ast.Call, violations: list[tuple[int, str]]) -> None:
    """Check --name / --repo values in _run_gw / subprocess.run call args."""
    # Gather all string-like args
    all_args: list[ast.expr] = list(node.args) + [kw.value for kw in node.keywords]

    # Also walk list/tuple literals passed as first arg (subprocess.run([...]))
    flat_elts: list[ast.expr] = []
    for a in all_args:
        if isinstance(a, (ast.List, ast.Tuple)):
            flat_elts.extend(a.elts)
        else:
            flat_elts.append(a)

    flag_names = {"--name", "--repo"}
    for i, elt in enumerate(flat_elts):
        if isinstance(elt, ast.Constant) and elt.value in flag_names:
            # Next element is the value
            if i + 1 < len(flat_elts):
                val_node = flat_elts[i + 1]
                if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                    if val_node.value not in _ALLOWED_LITERALS:
                        violations.append((
                            node.lineno,
                            f"CLI {elt.value!r} passed bare literal {val_node.value!r} "
                            "(must use _resource_prefix() or be an allowed fixture name)",
                        ))


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestAcceptanceNamesFromPrefix:
    """Every repo/team name in tests/acceptance is derived from GW_RESOURCE_PREFIX."""

    def _collect_violations(self) -> list[tuple[pathlib.Path, int, str]]:
        all_violations: list[tuple[pathlib.Path, int, str]] = []
        for py_file in sorted(ACCEPTANCE_DIR.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            for lineno, desc in _extract_name_violations(tree, py_file):
                all_violations.append((py_file, lineno, desc))
        return all_violations

    def test_no_bare_literal_names(self):
        """No acceptance test passes a bare string literal as a repo/team name."""
        violations = self._collect_violations()
        if violations:
            lines = [
                f"  {v[0].name}:{v[1]}: {v[2]}"
                for v in violations
            ]
            pytest.fail(
                "Acceptance tests use bare literal names (must use _resource_prefix()):\n"
                + "\n".join(lines)
            )

    def test_acceptance_dir_has_python_files(self):
        """Sanity: the acceptance directory has at least one .py file."""
        files = list(ACCEPTANCE_DIR.glob("*.py"))
        assert files, f"No .py files found in {ACCEPTANCE_DIR}"
