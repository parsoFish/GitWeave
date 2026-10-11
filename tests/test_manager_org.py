# tests/test_manager_org.py
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from gitweave.managers.org import OrgSettingsManager, ResourceStatus, ORG_DEFAULTS


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.description = "Test org"
    org.default_repository_permission = "write"
    org.web_commit_signoff_required = True
    org.members_can_create_repositories = False
    return org


@pytest.fixture
def manager(mock_org):
    return OrgSettingsManager(mock_org)


class TestApply:
    def test_calls_org_edit_with_declared_settings(self, manager, mock_org):
        """AC1: apply() calls org.edit() with the declared settings dict."""
        settings = {
            "description": "New description",
            "default_repository_permission": "read",
            "web_commit_signoff_required": False,
            "members_can_create_repositories": True,
        }
        manager.apply(settings)
        mock_org.edit.assert_called_once_with(**settings)

    def test_returns_status_ok_on_success(self, manager):
        """AC1: apply() returns ResourceStatus with status=ok."""
        settings = {"description": "test"}
        result = manager.apply(settings)
        assert isinstance(result, ResourceStatus)
        assert result.status == "ok"
        assert result.name == "org_settings"
        assert result.error is None

    def test_returns_status_error_on_exception(self, manager, mock_org):
        """AC3: apply() returns status=error when org.edit() raises."""
        mock_org.edit.side_effect = GithubException(422, {"message": "Validation failed"})
        settings = {"description": "bad"}
        result = manager.apply(settings)
        assert result.status == "error"
        assert result.name == "org_settings"
        assert result.error is not None
        assert "422" in result.error or "Validation" in result.error

    def test_does_not_propagate_exception(self, manager, mock_org):
        """AC3: exception is caught, not propagated."""
        mock_org.edit.side_effect = GithubException(500, {"message": "Server error"})
        result = manager.apply({})
        assert result.status == "error"


class TestReset:
    def test_calls_edit_with_org_defaults(self, manager, mock_org):
        """AC2: reset() calls org.edit() with ORG_DEFAULTS values."""
        manager.reset()
        mock_org.edit.assert_called_once_with(**ORG_DEFAULTS)

    def test_reset_defaults_are_correct(self, manager, mock_org):
        """AC2: ORG_DEFAULTS match expected GitHub safe defaults."""
        manager.reset()
        call_kwargs = mock_org.edit.call_args.kwargs
        assert call_kwargs["description"] == ""
        assert call_kwargs["default_repository_permission"] == "read"
        assert call_kwargs["web_commit_signoff_required"] is False
        assert call_kwargs["members_can_create_repositories"] is True

    def test_reset_returns_status_ok(self, manager):
        """AC2: reset() returns ok status on success."""
        result = manager.reset()
        assert result.status == "ok"


class TestCurrent:
    def test_reads_org_attributes(self, manager, mock_org):
        """current() returns live org settings as dict."""
        result = manager.current()
        assert result["description"] == "Test org"
        assert result["default_repository_permission"] == "write"
        assert result["web_commit_signoff_required"] is True
        assert result["members_can_create_repositories"] is False

    def test_normalises_none_description(self, mock_org):
        """current() converts None description to empty string."""
        mock_org.description = None
        mgr = OrgSettingsManager(mock_org)
        result = mgr.current()
        assert result["description"] == ""
