"""Tests for caller-identity auth primitives (WI-2)."""

import io
import json
import os
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from gitweave.auth import CallerTokenRequiredError, get_caller_token, resolve_caller_login


class TestCallerAuth:
    """AC1–AC5: caller token resolution and login resolution."""

    # --- AC1 ---
    def test_env_token_returned_directly(self, monkeypatch):
        """GW_CALLER_TOKEN set → return it without invoking gh."""
        monkeypatch.setenv("GW_CALLER_TOKEN", "tok_env_abc123")
        with patch("subprocess.run") as mock_run:
            result = get_caller_token()
        assert result == "tok_env_abc123"
        mock_run.assert_not_called()

    # --- AC2 ---
    def test_gh_auth_token_fallback(self, monkeypatch):
        """GW_CALLER_TOKEN unset → fall back to 'gh auth token'."""
        monkeypatch.delenv("GW_CALLER_TOKEN", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_from_gh_cli\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = get_caller_token()
        assert result == "ghp_from_gh_cli"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["gh", "auth", "token"]

    # --- AC3 ---
    def test_missing_token_raises(self, monkeypatch):
        """GW_CALLER_TOKEN unset and gh fails → CallerTokenRequiredError."""
        monkeypatch.delenv("GW_CALLER_TOKEN", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(CallerTokenRequiredError) as exc_info:
                get_caller_token()
        assert "caller-token-required" in str(exc_info.value)

    def test_missing_token_raises_on_empty_stdout(self, monkeypatch):
        """gh exits 0 but returns empty string → CallerTokenRequiredError."""
        monkeypatch.delenv("GW_CALLER_TOKEN", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   \n"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(CallerTokenRequiredError) as exc_info:
                get_caller_token()
        assert "caller-token-required" in str(exc_info.value)

    def test_missing_token_never_returns_none(self, monkeypatch):
        """get_caller_token never returns None."""
        monkeypatch.delenv("GW_CALLER_TOKEN", raising=False)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(CallerTokenRequiredError):
                get_caller_token()

    # --- AC4 ---
    def test_resolve_caller_login_success(self):
        """Valid token → return login from /user JSON."""
        body = json.dumps({"login": "octocat", "id": 1}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            login = resolve_caller_login("tok_valid")
        assert login == "octocat"

    # --- AC5 ---
    def test_resolve_caller_login_401_raises(self):
        """GitHub 401 → CallerTokenRequiredError."""
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/user",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(CallerTokenRequiredError) as exc_info:
                resolve_caller_login("tok_bad")
        assert "caller-token-required" in str(exc_info.value)
