"""tests/test_plan.py — unit tests for gitweave.plan diff engine.

All tests use fixture files or in-memory dicts; zero live network calls.
"""

from __future__ import annotations

import json
import os
import pathlib
from unittest.mock import patch, MagicMock

import pytest

from gitweave.plan import plan, PlanResult, PlanItem, _diff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent
ORG_EMPTY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "org-empty.json"


def _cfg_with_teams_and_rulesets() -> dict:
    """Return a minimal config dict with one team and one ruleset declared."""
    return {
        "org_settings": {
            "description": "",
            "default_repository_permission": "read",
            "web_commit_signoff_required": False,
            "members_can_create_repositories": True,
        },
        "teams": [{"name": "engineering"}],
        "repos": [],
        "rulesets": [{"name": "forge-main-protection"}],
    }


def _matching_snapshot(cfg: dict) -> dict:
    """Build a snapshot that exactly mirrors the declared config."""
    return {
        "org_settings": cfg["org_settings"].copy(),
        "teams": [{"name": t["name"]} for t in cfg["teams"]],
        "repos": [],
        "rulesets": [{"name": r["name"]} for r in cfg["rulesets"]],
    }


# ---------------------------------------------------------------------------
# AC1: org-empty fixture → all declared resources are 'create'
# ---------------------------------------------------------------------------


def test_plan_empty_fixture_all_create(tmp_path, monkeypatch):
    """AC1: fixture with empty org → every declared resource is a 'create' action."""
    assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

    # Ensure prefix filtering doesn't hide unqualified names used in test fixtures.
    monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
    monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "")

    # Patch load_config to return a known config (avoids depending on live config files)
    cfg = _cfg_with_teams_and_rulesets()

    with patch("gitweave.plan.load_config", return_value=cfg):
        result = plan(fixture_path=str(ORG_EMPTY_FIXTURE))

    assert isinstance(result, PlanResult)
    actions = {(item.resource_type, item.name): item.action for item in result.items}

    # The empty fixture has no teams or rulesets → both should be 'create'
    assert actions[("team", "engineering")] == "create"
    assert actions[("ruleset", "forge-main-protection")] == "create"

    # org-empty.json has matching org_settings → unchanged
    assert actions[("org_settings", "org_settings")] == "unchanged"


def test_plan_empty_fixture_zero_network_calls(tmp_path):
    """AC1 + AC3: fixture mode makes zero network calls."""
    cfg = _cfg_with_teams_and_rulesets()

    with patch("gitweave.plan.load_config", return_value=cfg):
        with patch("gitweave.plan.get_github_client") as mock_gh:
            result = plan(fixture_path=str(ORG_EMPTY_FIXTURE))

    mock_gh.assert_not_called()
    assert isinstance(result, PlanResult)


# ---------------------------------------------------------------------------
# AC2: matching snapshot → all 'unchanged'
# ---------------------------------------------------------------------------


def test_plan_matching_snapshot_all_unchanged(tmp_path):
    """AC2: fixture that mirrors declared config → all items are 'unchanged'."""
    cfg = _cfg_with_teams_and_rulesets()
    snapshot = _matching_snapshot(cfg)

    fixture_file = tmp_path / "full.json"
    fixture_file.write_text(json.dumps(snapshot))

    with patch("gitweave.plan.load_config", return_value=cfg):
        result = plan(fixture_path=str(fixture_file))

    actions = [item.action for item in result.items]
    assert all(a == "unchanged" for a in actions), f"Expected all unchanged, got: {result.items}"


# ---------------------------------------------------------------------------
# AC3: fixture + GW_* set → fixture wins, no network
# ---------------------------------------------------------------------------


def test_plan_fixture_exclusive_when_gw_vars_set(tmp_path, monkeypatch):
    """AC3: fixture_path wins over GW_* — no network calls even when GW_ORG is set."""
    monkeypatch.setenv("GW_ORG", "some-org")
    monkeypatch.setenv("GW_APP_ID", "12345")

    cfg = _cfg_with_teams_and_rulesets()
    snapshot = _matching_snapshot(cfg)

    fixture_file = tmp_path / "snap.json"
    fixture_file.write_text(json.dumps(snapshot))

    with patch("gitweave.plan.load_config", return_value=cfg):
        with patch("gitweave.plan.get_github_client") as mock_gh:
            result = plan(fixture_path=str(fixture_file))

    mock_gh.assert_not_called()
    assert isinstance(result, PlanResult)


# ---------------------------------------------------------------------------
# AC4: no fixture, GW_ORG unset → EnvironmentError naming GW_ORG
# ---------------------------------------------------------------------------


def test_plan_raises_env_error_without_gw_org(monkeypatch):
    """AC4: no fixture and GW_ORG unset raises EnvironmentError mentioning GW_ORG."""
    monkeypatch.delenv("GW_ORG", raising=False)

    cfg = _cfg_with_teams_and_rulesets()

    with patch("gitweave.plan.load_config", return_value=cfg):
        with pytest.raises(EnvironmentError, match="GW_ORG"):
            plan()


# ---------------------------------------------------------------------------
# Bonus: resource in snapshot but not in config → 'delete'
# ---------------------------------------------------------------------------


def test_plan_extra_snapshot_resource_is_delete(tmp_path, monkeypatch):
    """Resource present in snapshot but absent from declared config → 'delete'."""
    # Ensure prefix filtering doesn't hide unqualified names used in test fixtures.
    monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
    monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "")

    cfg = _cfg_with_teams_and_rulesets()
    snapshot = _matching_snapshot(cfg)
    # Add an extra team not declared in config
    snapshot["teams"].append({"name": "ghost-team"})

    fixture_file = tmp_path / "extra.json"
    fixture_file.write_text(json.dumps(snapshot))

    with patch("gitweave.plan.load_config", return_value=cfg):
        result = plan(fixture_path=str(fixture_file))

    actions = {(item.resource_type, item.name): item.action for item in result.items}
    assert actions[("team", "ghost-team")] == "delete"
    assert actions[("team", "engineering")] == "unchanged"


# ---------------------------------------------------------------------------
# Direct _diff tests (no I/O)
# ---------------------------------------------------------------------------


def test_diff_create_update_unchanged():
    """_diff returns correct mix of create/update/unchanged actions."""
    cfg = {
        "org_settings": {"key": "value"},
        "teams": [{"name": "alpha"}, {"name": "beta"}],
        "repos": [],
        "rulesets": [],
    }
    snapshot = {
        "org_settings": {},  # differs → update
        "teams": [{"name": "beta"}],  # alpha missing → create
        "repos": [],
        "rulesets": [],
    }
    result = _diff(cfg, snapshot, prefix="")
    action_map = {(i.resource_type, i.name): i.action for i in result.items}

    assert action_map[("org_settings", "org_settings")] == "update"
    assert action_map[("team", "alpha")] == "create"
    assert action_map[("team", "beta")] == "unchanged"


# ---------------------------------------------------------------------------
# AC7 — rulesets unsupported in JSON output
# ---------------------------------------------------------------------------


class TestPlanResultRulesetsUnsupportedJson:
    """AC7: when org plan lacks rulesets, to_json() reports 'unsupported'."""

    def test_to_json_rulesets_unsupported_string(self):
        """rulesets_unsupported set → JSON rulesets field is 'unsupported: <msg>'."""
        r = PlanResult()
        r.rulesets_unsupported = "Upgrade to GitHub Team to enable this feature."
        data = json.loads(r.to_json())
        rulesets = data["rulesets"]
        assert isinstance(rulesets, str), f"expected str, got {type(rulesets)}"
        assert "unsupported" in rulesets
        assert "Upgrade to GitHub" in rulesets

    def test_to_json_rulesets_unsupported_empty_when_supported(self):
        """rulesets_unsupported unset → JSON rulesets field is a list."""
        r = PlanResult()
        data = json.loads(r.to_json())
        assert isinstance(data["rulesets"], list)

    def test_live_snapshot_unsupported_propagates_to_plan_result(self, monkeypatch):
        """_live_snapshot catches RulesetsUnsupportedError and plan() propagates it."""
        from github import GithubException
        from gitweave.managers.rulesets import RulesetsUnsupportedError

        monkeypatch.setenv("GW_ORG", "test-org")
        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-")

        mock_org = MagicMock()
        mock_org.login = "test-org"

        # Teams mock: list_managed returns []
        mock_teams_mgr = MagicMock()
        mock_teams_mgr.list_managed.return_value = []

        # Rulesets mock: list_managed raises RulesetsUnsupportedError
        plan_lacking_msg = "Upgrade to GitHub Team to enable this feature."
        mock_rulesets_mgr = MagicMock()
        mock_rulesets_mgr.list_managed.side_effect = RulesetsUnsupportedError(plan_lacking_msg)

        cfg = {
            "org_settings": {},
            "teams": [],
            "repos": [],
            "rulesets": [],
            "overlay_repos": [],
        }

        with (
            patch("gitweave.plan.get_github_client") as mock_gh,
            patch("gitweave.plan.load_config", return_value=cfg),
            patch("gitweave.managers.teams.TeamsManager", return_value=mock_teams_mgr),
            patch("gitweave.managers.rulesets.RulesetsManager", return_value=mock_rulesets_mgr),
        ):
            mock_gh.return_value.get_organization.return_value = mock_org
            result = plan()

        assert result.rulesets_unsupported == plan_lacking_msg
        data = json.loads(result.to_json())
        assert "unsupported" in data["rulesets"]
        assert "Upgrade to GitHub" in data["rulesets"]
