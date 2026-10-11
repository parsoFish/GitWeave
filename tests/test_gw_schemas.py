import json
import pathlib

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).parent.parent


def _load_schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def _load_yaml(path):
    return yaml.safe_load((ROOT / path).read_text())


def test_org_schema_validates_org_yaml():
    jsonschema.validate(_load_yaml("config/org.yaml"), _load_schema("org.schema.json"))


def test_teams_schema_validates_teams_yaml():
    jsonschema.validate(_load_yaml("config/teams.yaml"), _load_schema("teams.schema.json"))


def test_ruleset_schema_validates_rulesets_yaml():
    jsonschema.validate(
        _load_yaml("config/rulesets.yaml"), _load_schema("org-ruleset.schema.json")
    )


def test_org_empty_fixture_is_valid_json_with_expected_keys():
    data = json.loads((ROOT / "tests/fixtures/org-empty.json").read_text())
    for key in ("org_settings", "teams", "repos", "rulesets"):
        assert key in data
    assert data["teams"] == []
    assert data["repos"] == []
    assert data["rulesets"] == []
