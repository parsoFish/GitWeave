"""Tests for gitweave.auth.get_github_client()."""

import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

import pytest

from gitweave.auth import REQUIRED_ENV, get_github_client

_ALL_ENV = {
    "GW_APP_ID": "123",
    "GW_APP_PRIVATE_KEY_PATH": "/fake/key.pem",
    "GW_APP_INSTALLATION_ID": "456",
    "GW_ORG": "my-org",
}
_FAKE_KEY = b"-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"


class TestGetGithubClientSuccess:
    """AC1: all env vars set → returns Github instance."""

    def test_returns_github_instance(self, tmp_path):
        key_file = tmp_path / "key.pem"
        key_file.write_bytes(_FAKE_KEY)

        env = {**_ALL_ENV, "GW_APP_PRIVATE_KEY_PATH": str(key_file)}

        with patch.dict(os.environ, env, clear=False):
            with patch("gitweave.auth.Auth.AppAuth") as mock_app_auth_cls:
                with patch("gitweave.auth.Auth.AppInstallationAuth") as mock_inst_auth_cls:
                    with patch("gitweave.auth.Github") as mock_github_cls:
                        mock_app_auth_instance = MagicMock()
                        mock_app_auth_cls.return_value = mock_app_auth_instance
                        mock_inst_auth_instance = MagicMock()
                        mock_inst_auth_cls.return_value = mock_inst_auth_instance
                        mock_github_instance = MagicMock()
                        mock_github_cls.return_value = mock_github_instance

                        result = get_github_client()

        # PyGithub 2.x two-step: AppAuth first, then AppInstallationAuth(app_auth=...)
        mock_app_auth_cls.assert_called_once_with(
            app_id=123,
            private_key=_FAKE_KEY.decode(),  # auth.py reads key as text (mode "r")
        )
        mock_inst_auth_cls.assert_called_once_with(
            app_auth=mock_app_auth_instance,
            installation_id=456,
        )
        mock_github_cls.assert_called_once_with(auth=mock_inst_auth_instance)
        assert result is mock_github_instance


class TestGetGithubClientMissingEnv:
    """AC2: missing env var → EnvironmentError naming the variable."""

    @pytest.mark.parametrize("missing_var", REQUIRED_ENV)
    def test_raises_env_error_for_each_missing_var(self, missing_var, tmp_path):
        key_file = tmp_path / "key.pem"
        key_file.write_bytes(_FAKE_KEY)

        env = {**_ALL_ENV, "GW_APP_PRIVATE_KEY_PATH": str(key_file)}
        env_without = {k: v for k, v in env.items() if k != missing_var}

        # Remove missing_var from environment entirely
        clean_env = {k: v for k, v in os.environ.items() if k not in REQUIRED_ENV}
        clean_env.update(env_without)

        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                get_github_client()

        assert missing_var in str(exc_info.value)

    def test_raises_env_error_all_missing(self):
        clean_env = {k: v for k, v in os.environ.items() if k not in REQUIRED_ENV}
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                get_github_client()

        error_msg = str(exc_info.value)
        for var in REQUIRED_ENV:
            assert var in error_msg


class TestGetGithubClientMissingKeyFile:
    """AC3: private key path does not exist → FileNotFoundError or EnvironmentError."""

    def test_raises_when_key_file_absent(self):
        env = {**_ALL_ENV, "GW_APP_PRIVATE_KEY_PATH": "/nonexistent/path/key.pem"}

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises((FileNotFoundError, EnvironmentError)) as exc_info:
                get_github_client()

        # Message should be descriptive
        assert len(str(exc_info.value)) > 0
