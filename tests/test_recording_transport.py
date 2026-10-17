"""Tests for gitweave.transport.RecordingTransport."""

import unittest

from gitweave.transport import RecordedRequest, RecordingTransport


def _fake_github_handler(method, url, **kwargs):
    """Stub handler: returns a simple dict as a response object."""
    return {"method": method, "url": url, "status": 200}


def _fake_overlay_apply_handler(method, url, **kwargs):
    """Stub handler simulating overlay apply (create branch) calls only — no PR open."""
    # overlay apply creates a branch via PATCH refs, never opens a PR
    if method.upper() == "POST" and url.endswith("/pulls"):
        raise AssertionError("overlay apply must not call POST .../pulls")
    return {"method": method, "url": url, "status": 200}


def _fake_self_serve_handler(method, url, **kwargs):
    """Stub handler simulating self-serve overlay request calls."""
    return {"method": method, "url": url, "status": 201}


def _fake_mutant_handler(method, url, **kwargs):
    """Mutant: opens a PR regardless of intent — to prove detection."""
    return {"method": method, "url": url, "status": 201}


class TestRecordingTransport(unittest.TestCase):
    # No GW_* autouse fixtures — unit tests only

    def test_zero_post_repos_pulls_overlay_path(self):
        """AC1: overlay apply path must not open any PRs."""
        transport = RecordingTransport(handler=_fake_overlay_apply_handler)

        # Simulate the calls an overlay apply (create branch) makes
        transport.request("PATCH", "https://api.github.com/repos/org/repo/git/refs/heads/main")
        transport.request("GET", "https://api.github.com/repos/org/repo/branches/main")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/refs")

        # No PR open should have been made
        transport.assert_no_pr_opens()

    def test_mutant_pr_open_detected(self):
        """AC2: a mutant that opens a PR is caught by assert_no_pr_opens."""
        transport = RecordingTransport(handler=_fake_mutant_handler)

        # Mutant overlay apply path that incorrectly opens a PR
        transport.request("GET", "https://api.github.com/repos/org/repo/branches/main")
        transport.request("POST", "https://api.github.com/repos/org/repo/pulls")

        with self.assertRaises(AssertionError) as ctx:
            transport.assert_no_pr_opens()

        self.assertIn("POST /repos/*/pulls", str(ctx.exception))

    def test_records_all_http_calls(self):
        """AC3 (partial): transport.requests grows with each call."""
        transport = RecordingTransport(handler=_fake_github_handler)

        transport.request("GET", "https://api.github.com/repos/org/repo")
        self.assertEqual(len(transport.requests), 1)

        transport.request("POST", "https://api.github.com/repos/org/repo/git/refs")
        self.assertEqual(len(transport.requests), 2)

        req = transport.requests[0]
        self.assertIsInstance(req, RecordedRequest)
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.url, "https://api.github.com/repos/org/repo")

    def test_filter_by_method_and_pattern(self):
        """filter() returns correct subset by method and URL glob."""
        transport = RecordingTransport(handler=_fake_github_handler)

        transport.request("GET", "https://api.github.com/repos/org/repo/branches/main")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/refs")
        transport.request("GET", "https://api.github.com/orgs/org/members")

        gets = transport.filter("GET", "https://api.github.com/repos/*/branches/*")
        self.assertEqual(len(gets), 1)
        self.assertEqual(gets[0].url, "https://api.github.com/repos/org/repo/branches/main")

        posts = transport.filter("POST", "https://api.github.com/repos/*/git/refs")
        self.assertEqual(len(posts), 1)

    def test_self_serve_path_intercepted(self):
        """AC3: self-serve path calls are captured in the same request log."""
        transport = RecordingTransport(handler=_fake_self_serve_handler)

        # Simulate self-serve overlay request calls
        transport.request("GET", "https://api.github.com/repos/org/new-repo")
        transport.request("POST", "https://api.github.com/orgs/org/repos")
        transport.request("PATCH", "https://api.github.com/repos/org/new-repo/topics")

        self.assertEqual(len(transport.requests), 3)
        methods = [r.method for r in transport.requests]
        self.assertEqual(methods, ["GET", "POST", "PATCH"])

        # Self-serve path also must not open PRs
        transport.assert_no_pr_opens()

    def test_both_paths_share_request_log(self):
        """AC3: overlay apply and self-serve paths share one transport log."""
        transport = RecordingTransport(handler=_fake_github_handler)

        # self-serve path
        transport.request("GET", "https://api.github.com/repos/org/repo")
        transport.request("POST", "https://api.github.com/orgs/org/repos")

        # overlay apply path
        transport.request("PATCH", "https://api.github.com/repos/org/repo/git/refs/heads/main")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/refs")

        self.assertEqual(len(transport.requests), 4)
        transport.assert_no_pr_opens()


if __name__ == "__main__":
    unittest.main()
