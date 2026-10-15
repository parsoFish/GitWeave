"""gitweave.config — load and validate all config files."""

import json
import pathlib

import jsonschema
import yaml

REPO_ROOT = pathlib.Path(__file__).parent.parent

SCHEMA_MAP = {
    "org_settings": "schemas/org.schema.json",
    "teams": "schemas/teams.schema.json",
    "rulesets": "schemas/org-ruleset.schema.json",
}


def _load_yaml(rel: str, root: pathlib.Path = REPO_ROOT) -> dict:
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return yaml.safe_load(path.read_text()) or {}


def _load_schema(rel: str, root: pathlib.Path = REPO_ROOT) -> dict:
    return json.loads((root / rel).read_text())


def load_config(root: pathlib.Path = REPO_ROOT) -> dict:
    """Load and validate all config files. Returns unified config dict."""
    org_raw = _load_yaml("config/org.yaml", root)
    jsonschema.validate(org_raw, _load_schema("schemas/org.schema.json", root))

    teams_raw = _load_yaml("config/teams.yaml", root)
    jsonschema.validate(teams_raw, _load_schema("schemas/teams.schema.json", root))

    rulesets_raw = _load_yaml("config/rulesets.yaml", root)
    jsonschema.validate(rulesets_raw, _load_schema("schemas/org-ruleset.schema.json", root))

    # Repos: scan config/repos/*.yaml (no top-level schema enforced yet).
    # Skip overlay YAML files (identified by an `apiVersion` key — those are
    # for apply-overlays.py, not for gitweave's repo manager).
    repos = []
    repos_dir = root / "config" / "repos"
    if repos_dir.exists():
        for f in sorted(repos_dir.glob("*.yaml")):
            repo_cfg = yaml.safe_load(f.read_text()) or {}
            if "apiVersion" in repo_cfg:
                continue
            repo_cfg.setdefault("slug", f.stem)
            repos.append(repo_cfg)

    return {
        "org_settings": org_raw,
        "teams": teams_raw.get("teams", []),
        "repos": repos,
        "rulesets": rulesets_raw.get("rulesets", []),
    }
