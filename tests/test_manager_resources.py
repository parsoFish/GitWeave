"""Tests for TeamsManager, ReposManager, RulesetsManager — WI-5b.

Updated for GW_RESOURCE_PREFIX as primary marker; FORGE_RESOURCE_PREFIX is
optional narrowing only.
"""
import os
from unittest.mock import MagicMock, call

import pytest

from gitweave.managers.teams import TeamsManager, _get_prefix
from gitweave.managers.repos import ReposManager
from gitweave.managers.rulesets import RulesetsManager
from gitweave.managers.org import ResourceStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_team(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    return t


def _make_repo(name: str) -> MagicMock:
    r = MagicMock()
    r.name = name
    return r


# ---------------------------------------------------------------------------
# _get_prefix — GW_RESOURCE_PREFIX is now primary
# ---------------------------------------------------------------------------


def test_get_prefix_raises_when_gw_unset(monkeypatch):
    monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
        _get_prefix()


def test_get_prefix_raises_when_gw_empty(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
        _get_prefix()


def test_get_prefix_returns_gw_prefix_when_forge_unset(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    assert _get_prefix() == "gw-test-"



# ---------------------------------------------------------------------------
# Instantiation raises when GW_RESOURCE_PREFIX unset / empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("Manager", [TeamsManager, ReposManager, RulesetsManager])
def test_instantiation_raises_when_gw_prefix_unset(monkeypatch, Manager):
    monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
        Manager(org)


@pytest.mark.parametrize("Manager", [TeamsManager, ReposManager, RulesetsManager])
def test_instantiation_raises_when_gw_prefix_empty(monkeypatch, Manager):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
        Manager(org)


# ---------------------------------------------------------------------------
# AC1: TeamsManager.list_managed() filters by GW_RESOURCE_PREFIX
# ---------------------------------------------------------------------------


def test_list_managed_returns_prefix_teams(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_teams.return_value = [
        _make_team("forge-eng"),
        _make_team("forge-qa"),
        _make_team("other-team"),
    ]
    mgr = TeamsManager(org)
    result = mgr.list_managed()
    assert len(result) == 2
    names = {t.name for t in result}
    assert names == {"forge-eng", "forge-qa"}


def test_list_managed_empty_when_no_prefix_match(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_teams.return_value = [_make_team("other-team")]
    mgr = TeamsManager(org)
    assert mgr.list_managed() == []


# ---------------------------------------------------------------------------
# AC2: TeamsManager.apply() creates team when absent
# ---------------------------------------------------------------------------


def test_apply_creates_team_when_absent(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_teams.return_value = []  # no existing teams
    mgr = TeamsManager(org)
    cfg = {"name": "forge-backend", "description": "Backend", "privacy": "closed"}
    result = mgr.apply(cfg)
    org.create_team.assert_called_once_with(
        "forge-backend", description="Backend", privacy="closed"
    )
    assert isinstance(result, ResourceStatus)
    assert result.status == "ok"
    assert result.name == "forge-backend"


def test_apply_updates_team_when_present(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    existing_team = _make_team("forge-backend")
    org = MagicMock()
    org.get_teams.return_value = [existing_team]
    mgr = TeamsManager(org)
    cfg = {"name": "forge-backend", "description": "Updated", "privacy": "closed"}
    result = mgr.apply(cfg)
    existing_team.edit.assert_called_once()
    org.create_team.assert_not_called()
    assert result.status == "ok"


def test_apply_returns_error_on_exception(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_teams.side_effect = RuntimeError("API down")
    mgr = TeamsManager(org)
    result = mgr.apply({"name": "forge-x"})
    assert result.status == "error"
    assert "API down" in result.error


# ---------------------------------------------------------------------------
# TeamsManager.delete()
# ---------------------------------------------------------------------------


def test_delete_team_treats_404_as_success(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_teams.side_effect = Exception("404 Not Found")
    mgr = TeamsManager(org)
    result = mgr.delete("forge-gone")
    assert result.status == "ok"


# ---------------------------------------------------------------------------
# AC4: ReposManager.apply() creates repo when absent
# ---------------------------------------------------------------------------


def test_repos_apply_creates_repo_when_absent(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_repos.return_value = []
    mgr = ReposManager(org)
    cfg = {"slug": "forge-api", "description": "API repo", "private": True}
    result = mgr.apply(cfg)
    org.create_repo.assert_called_once_with(
        "forge-api",
        description="API repo",
        private=True,
        has_issues=True,
        has_projects=True,
    )
    assert result.status == "ok"
    assert result.name == "forge-api"


def test_repos_apply_updates_repo_when_present(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    existing_repo = _make_repo("forge-api")
    org = MagicMock()
    org.get_repos.return_value = [existing_repo]
    mgr = ReposManager(org)
    cfg = {"slug": "forge-api", "description": "Updated", "private": False}
    result = mgr.apply(cfg)
    existing_repo.edit.assert_called_once()
    org.create_repo.assert_not_called()
    assert result.status == "ok"


def test_repos_apply_returns_error_on_exception(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_repos.side_effect = RuntimeError("quota exceeded")
    mgr = ReposManager(org)
    result = mgr.apply({"slug": "forge-x"})
    assert result.status == "error"
    assert "quota exceeded" in result.error


def test_repos_delete_treats_404_as_success(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.get_repos.side_effect = Exception("404 Not Found")
    mgr = ReposManager(org)
    result = mgr.delete("forge-gone")
    assert result.status == "ok"


# ---------------------------------------------------------------------------
# AC5: RulesetsManager.apply() calls org rulesets API
# ---------------------------------------------------------------------------


def _make_ruleset_org(existing_rulesets=None):
    """Build a mock org whose _requester returns given ruleset list."""
    org = MagicMock()
    org.login = "my-org"
    if existing_rulesets is None:
        existing_rulesets = []
    # list_managed relies on requestJsonAndCheck returning (headers, list)
    org._requester.requestJsonAndCheck.return_value = ({}, existing_rulesets)
    return org


def test_rulesets_apply_creates_when_absent(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = _make_ruleset_org(existing_rulesets=[])
    mgr = RulesetsManager(org)
    cfg = {"name": "forge-branch-protection", "target": "branch"}
    result = mgr.apply(cfg)
    # Should POST to create
    calls = org._requester.requestJsonAndCheck.call_args_list
    post_calls = [c for c in calls if c.args[0] == "POST"]
    assert len(post_calls) == 1
    assert "/orgs/my-org/rulesets" in post_calls[0].args[1]
    assert result.status == "ok"
    assert result.name == "forge-branch-protection"


def test_rulesets_apply_updates_when_present(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    existing = [{"name": "forge-branch-protection", "id": 42}]
    org = _make_ruleset_org(existing_rulesets=existing)
    mgr = RulesetsManager(org)
    cfg = {"name": "forge-branch-protection", "target": "branch"}
    result = mgr.apply(cfg)
    put_calls = [
        c for c in org._requester.requestJsonAndCheck.call_args_list
        if c.args[0] == "PUT"
    ]
    assert len(put_calls) == 1
    assert "42" in put_calls[0].args[1]
    assert result.status == "ok"


def test_rulesets_apply_returns_error_on_exception(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    org = MagicMock()
    org.login = "my-org"
    org._requester.requestJsonAndCheck.side_effect = RuntimeError("rate limited")
    mgr = RulesetsManager(org)
    result = mgr.apply({"name": "forge-x"})
    assert result.status == "error"
    assert "rate limited" in result.error


def test_rulesets_list_managed_filters_by_prefix(monkeypatch):
    monkeypatch.setenv("GW_RESOURCE_PREFIX", "forge-")
    monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
    all_rulesets = [
        {"name": "forge-branch-protection", "id": 1},
        {"name": "other-rule", "id": 2},
    ]
    org = _make_ruleset_org(existing_rulesets=all_rulesets)
    mgr = RulesetsManager(org)
    result = mgr.list_managed()
    assert len(result) == 1
    assert result[0]["name"] == "forge-branch-protection"
