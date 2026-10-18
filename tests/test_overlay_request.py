"""Tests for gitweave.self_serve.overlay_request — WI-9."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from gitweave.policy import PolicyError
from gitweave.self_serve.overlay_request import (
    OverlayRequestDenied,
    self_serve_overlay_request,
)
from gitweave.transport import RecordingTransport


def _noop_handler(method, url, **kwargs):
    return {"method": method, "url": url, "status": 200}


def _make_mock_apply_result(action="created"):
    result = MagicMock()
    result.action = action
    return result


class TestOverlayRequest(unittest.TestCase):
    """Unit tests for self_serve_overlay_request and CLI wiring."""

    # ------------------------------------------------------------------
    # AC1: allowed module → applied with no PR
    # ------------------------------------------------------------------

    def test_allowed_module_applied_no_pr(self):
        """Allowed module is applied; transport records zero PR-open calls."""
        transport = RecordingTransport(handler=_noop_handler)

        mock_policy = MagicMock()
        mock_policy.allowed_modules_for_team.return_value = ["python_service"]

        mock_org = MagicMock()
        mock_org.login = "test-org"

        apply_result = _make_mock_apply_result("created")

        with patch(
            "gitweave.self_serve.overlay_request.apply_module_to_repo",
            return_value=apply_result,
        ):
            result = self_serve_overlay_request(
                team="team-a",
                repo="target-repo",
                module_name="python_service",
                gh_org=mock_org,
                policy=mock_policy,
                caller_login="user@example.com",
                transport=transport,
            )

        # No PR-open calls on the recording transport
        transport.assert_no_pr_opens()

        self.assertEqual(result["module"], "python_service")
        self.assertEqual(result["repo"], "target-repo")
        self.assertEqual(result["action"], "created")
        mock_policy.allowed_modules_for_team.assert_called_once_with("team-a")

    # ------------------------------------------------------------------
    # AC2: denied module → OverlayRequestDenied, zero write calls
    # ------------------------------------------------------------------

    def test_denied_module_raises_with_rule_name(self):
        """Module not in allowed_modules raises OverlayRequestDenied with rule name."""
        transport = RecordingTransport(handler=_noop_handler)

        mock_policy = MagicMock()
        mock_policy.allowed_modules_for_team.return_value = []  # terraform_module absent

        mock_org = MagicMock()
        mock_org.login = "test-org"

        with self.assertRaises(OverlayRequestDenied) as ctx:
            self_serve_overlay_request(
                team="team-a",
                repo="target-repo",
                module_name="terraform_module",
                gh_org=mock_org,
                policy=mock_policy,
                caller_login="user@example.com",
                transport=transport,
            )

        # Rule name must appear in the error message
        self.assertIn("allowed_modules", str(ctx.exception))
        self.assertIn("terraform_module", str(ctx.exception))

        # Zero write calls recorded (refusal happens before any apply)
        write_calls = (
            transport.filter("POST", "*")
            + transport.filter("PUT", "*")
            + transport.filter("PATCH", "*")
        )
        self.assertEqual(write_calls, [])

    def test_denied_module_cli_exits_nonzero(self):
        """CLI exits 1 and prints rule name to stderr on policy denial."""
        with patch("gitweave.cli._self_serve_auth") as mock_auth:
            mock_org = MagicMock()
            mock_org.login = "test-org"
            mock_policy = MagicMock()
            mock_policy.allowed_modules_for_team.return_value = []
            mock_auth.return_value = (mock_org, mock_policy, "user")

            import io
            import argparse

            # Build args as the CLI would
            sys.argv = [
                "gw", "overlay", "request",
                "--team", "team-a",
                "--repo", "target-repo",
                "--module", "terraform_module",
            ]
            from gitweave.cli import cmd_overlay_request
            args = argparse.Namespace(
                team="team-a", repo="target-repo", module="terraform_module"
            )

            import io as _io
            from contextlib import redirect_stderr

            buf = _io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stderr(buf):
                    cmd_overlay_request(args)

            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("allowed_modules", buf.getvalue())

    # ------------------------------------------------------------------
    # AC3: policy absent → PolicyError (not FileNotFoundError), zero writes
    # ------------------------------------------------------------------

    def test_policy_absent_raises_policy_error(self):
        """When PolicyLoader.load raises PolicyError, function propagates it (not FileNotFoundError)."""
        transport = RecordingTransport(handler=_noop_handler)

        mock_policy = MagicMock()
        mock_policy.allowed_modules_for_team.side_effect = PolicyError(
            "Policy file not found: config/policy.yaml. "
            "Create config/policy.yaml to define team permissions."
        )

        mock_org = MagicMock()
        mock_org.login = "test-org"

        with self.assertRaises(PolicyError) as ctx:
            self_serve_overlay_request(
                team="team-a",
                repo="target-repo",
                module_name="python_service",
                gh_org=mock_org,
                policy=mock_policy,
                caller_login="user@example.com",
                transport=transport,
            )

        # Must be PolicyError, not FileNotFoundError
        self.assertIsInstance(ctx.exception, PolicyError)
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)

        # Zero write calls
        write_calls = (
            transport.filter("POST", "*")
            + transport.filter("PUT", "*")
            + transport.filter("PATCH", "*")
        )
        self.assertEqual(write_calls, [])

    def test_policy_absent_cli_exits_nonzero(self):
        """CLI exits 1 when policy is absent."""
        with patch("gitweave.cli._self_serve_auth") as mock_auth:
            mock_org = MagicMock()
            mock_org.login = "test-org"
            mock_policy = MagicMock()
            mock_policy.allowed_modules_for_team.side_effect = PolicyError(
                "Policy file not found: config/policy.yaml."
            )
            mock_auth.return_value = (mock_org, mock_policy, "user")

            import argparse
            import io
            from contextlib import redirect_stderr

            from gitweave.cli import cmd_overlay_request

            args = argparse.Namespace(
                team="team-a", repo="target-repo", module="python_service"
            )
            buf = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stderr(buf):
                    cmd_overlay_request(args)

            self.assertEqual(ctx.exception.code, 1)

    # ------------------------------------------------------------------
    # AC4: CLI parser — overlay request subcommand registered
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # AC12: no-PR assertion on the REAL self-serve request path
    # (apply_module_to_repo is NOT patched out in this test)
    # ------------------------------------------------------------------

    def test_allowed_module_real_apply_no_pr(self):
        """AC12: real apply_module_to_repo path opens no PRs; mutant that adds POST /pulls fails here."""
        from pathlib import Path
        from unittest.mock import patch as _patch

        CURRENT_SHA = "abc1234567890"
        TREE_SHA = "tree1234"
        NEW_TREE_SHA = "newtree5678"
        NEW_COMMIT_SHA = "newcommit9012"
        blob_counter = [0]

        def _full_handler(method: str, url: str, **kwargs):
            m = method.upper()
            if m == "GET" and "/.gitweave/" in url:
                return None  # no prior state
            if m == "GET" and "/git/refs/heads/" in url:
                return {"object": {"sha": CURRENT_SHA}}
            if m == "GET" and f"/git/commits/{CURRENT_SHA}" in url:
                return {"tree": {"sha": TREE_SHA}}
            if m == "POST" and url.endswith("/git/blobs"):
                blob_counter[0] += 1
                return {"sha": f"blob{blob_counter[0]:04d}"}
            if m == "POST" and url.endswith("/git/trees"):
                return {"sha": NEW_TREE_SHA}
            if m == "POST" and url.endswith("/git/commits"):
                return {"sha": NEW_COMMIT_SHA}
            if m == "PATCH" and "/git/refs/heads/" in url:
                return {"ref": "refs/heads/main", "object": {"sha": NEW_COMMIT_SHA}}
            if m == "POST" and url.endswith("/pulls"):
                # AC12: return data so assert_no_pr_opens can detect mutant
                return {"number": 99, "html_url": "https://github.com/test-org/target-repo/pull/99"}
            raise ValueError(f"Unexpected request in _full_handler: {m} {url}")

        transport = RecordingTransport(handler=_full_handler)

        mock_policy = MagicMock()
        mock_policy.allowed_modules_for_team.return_value = ["python_service"]

        mock_org = MagicMock()
        mock_org.login = "test-org"

        def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
            p = Path(dest)
            p.mkdir(parents=True, exist_ok=True)
            (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")

        with _patch("gitweave.managers.overlays.render_module", side_effect=_fake_render):
            result = self_serve_overlay_request(
                team="team-a",
                repo="target-repo",
                module_name="python_service",
                gh_org=mock_org,
                policy=mock_policy,
                caller_login="user@example.com",
                transport=transport,
            )

        # AC12: no PR should have been opened on the REAL apply path
        transport.assert_no_pr_opens()
        self.assertEqual(result["module"], "python_service")

    def test_request_help_exits_zero(self):
        """gw overlay request --help exits 0."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "overlay", "request", "--help"],
            capture_output=True,
            text=True,
        )
        # argparse exits 0 for --help
        self.assertEqual(result.returncode, 0)
        self.assertIn("--team", result.stdout)
        self.assertIn("--repo", result.stdout)
        self.assertIn("--module", result.stdout)


if __name__ == "__main__":
    unittest.main()
