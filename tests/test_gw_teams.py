"""
Replacement for the deleted TF team test suite.
Validates config/teams.yaml against its JSON schema, and tests that
gw plan --fixture runs cleanly credential-free.
"""
import json
import pathlib
import subprocess
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).parent.parent


def test_teams_yaml_validates_against_schema():
    """config/teams.yaml must satisfy schemas/teams.schema.json."""
    schema = json.loads((ROOT / "schemas" / "teams.schema.json").read_text())
    data = yaml.safe_load((ROOT / "config" / "teams.yaml").read_text())
    jsonschema.validate(data, schema)


def test_gw_plan_fixture_exits_zero():
    """gw plan --fixture tests/fixtures/org-empty.json exits 0 with no network calls."""
    result = subprocess.run(
        [sys.executable, "-m", "gitweave.cli",
         "plan", "--fixture", str(ROOT / "tests" / "fixtures" / "org-empty.json")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"gw plan --fixture exited {result.returncode}:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    # gw plan output marks new resources with leading "  + ", e.g. "  + team/engineering"
    assert any(line.strip().startswith("+ ") for line in result.stdout.splitlines()), (
        f"Expected creation lines (lines starting with '+ ') in output but got:\n{result.stdout}"
    )


def test_no_tf_team_test_files_remain():
    """All test_tf_teams_*.py files must be deleted by WI-9a."""
    tf_tests = list((ROOT / "tests").glob("test_tf_teams_*.py"))
    assert tf_tests == [], (
        f"TF team test files still present: {[str(p) for p in tf_tests]}"
    )
