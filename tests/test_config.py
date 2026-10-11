"""Tests for gitweave.config.load_config()."""

import pathlib
import json

import pytest
import yaml
import jsonschema

import gitweave.config as config_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_valid_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal valid config tree under tmp_path."""
    repo_root = tmp_path / "repo"

    # Copy schemas from the real repo
    real_root = pathlib.Path(__file__).parent.parent
    schemas_src = real_root / "schemas"
    schemas_dst = repo_root / "schemas"
    schemas_dst.mkdir(parents=True, exist_ok=True)
    for schema_file in schemas_src.glob("*.json"):
        (schemas_dst / schema_file.name).write_text(schema_file.read_text())

    # org.yaml
    _write(
        repo_root / "config" / "org.yaml",
        "description: test org\n"
        "default_repository_permission: read\n"
        "web_commit_signoff_required: false\n"
        "members_can_create_repositories: true\n",
    )

    # teams.yaml
    _write(
        repo_root / "config" / "teams.yaml",
        "teams:\n"
        "  - name: eng\n"
        "    description: Engineering\n"
        "    privacy: closed\n",
    )

    # rulesets.yaml
    _write(
        repo_root / "config" / "rulesets.yaml",
        "rulesets:\n"
        "  - name: main-protection\n"
        "    target: branch\n"
        "    enforcement: active\n"
        "    rules:\n"
        "      - type: required_linear_history\n",
    )

    return repo_root


# ---------------------------------------------------------------------------
# AC1: Valid config loads and returns correct keys
# ---------------------------------------------------------------------------

def test_load_config_returns_expected_keys(tmp_path):
    root = _build_valid_root(tmp_path)
    result = config_mod.load_config(root=root)

    assert set(result.keys()) == {"org_settings", "teams", "repos", "rulesets"}


def test_load_config_org_settings_populated(tmp_path):
    root = _build_valid_root(tmp_path)
    result = config_mod.load_config(root=root)

    assert result["org_settings"]["default_repository_permission"] == "read"


def test_load_config_teams_list(tmp_path):
    root = _build_valid_root(tmp_path)
    result = config_mod.load_config(root=root)

    assert isinstance(result["teams"], list)
    assert result["teams"][0]["name"] == "eng"


def test_load_config_rulesets_list(tmp_path):
    root = _build_valid_root(tmp_path)
    result = config_mod.load_config(root=root)

    assert isinstance(result["rulesets"], list)
    assert result["rulesets"][0]["name"] == "main-protection"


def test_load_config_repos_from_yaml_files(tmp_path):
    root = _build_valid_root(tmp_path)
    _write(
        root / "config" / "repos" / "my-repo.yaml",
        "visibility: private\n",
    )
    result = config_mod.load_config(root=root)

    assert len(result["repos"]) == 1
    assert result["repos"][0]["slug"] == "my-repo"
    assert result["repos"][0]["visibility"] == "private"


def test_load_config_repos_empty_when_no_repos_dir(tmp_path):
    root = _build_valid_root(tmp_path)
    result = config_mod.load_config(root=root)

    assert result["repos"] == []


# ---------------------------------------------------------------------------
# AC2: Invalid field raises jsonschema.ValidationError
# ---------------------------------------------------------------------------

def test_invalid_default_repository_permission_raises(tmp_path):
    root = _build_valid_root(tmp_path)
    # Overwrite org.yaml with an invalid value
    _write(
        root / "config" / "org.yaml",
        "description: test org\n"
        "default_repository_permission: invalid\n"
        "web_commit_signoff_required: false\n"
        "members_can_create_repositories: true\n",
    )

    with pytest.raises(jsonschema.ValidationError) as exc_info:
        config_mod.load_config(root=root)

    assert "invalid" in str(exc_info.value).lower() or "default_repository_permission" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC3: Missing config/org.yaml raises FileNotFoundError
# ---------------------------------------------------------------------------

def test_missing_org_yaml_raises_file_not_found(tmp_path):
    root = _build_valid_root(tmp_path)
    (root / "config" / "org.yaml").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        config_mod.load_config(root=root)

    assert "org.yaml" in str(exc_info.value)
