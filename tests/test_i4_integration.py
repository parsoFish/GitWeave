"""Integration tests confirming all I4 deliverables integrate correctly."""

import subprocess
import unittest


class FakeResponse:
    """Minimal response stub for RecordingTransport integration tests."""

    def __init__(self, method, url):
        self.method = method
        self.url = url
        self.status_code = 201 if method.upper() == "POST" else 200


class TestI4Integration(unittest.TestCase):
    """Integration gate for WI-12: all I4 modules importable, no-PR invariant holds."""

    def test_all_new_modules_importable(self):
        import gitweave.module_render
        import gitweave.transport
        import gitweave.managers.overlays
        import gitweave.self_serve.overlay_request

    def test_project_gate_passes(self):
        result = subprocess.run(
            [
                "python3", "-m", "pytest",
                "tests/test_structure.py",
                "tests/test_overlay_schema.py",
                "tests/test_copier_schema.py",
                "tests/test_copier_schema_ci.py",
                "--deselect",
                "tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero",
                "-q", "--tb=short",
            ],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_pr_invariant_combined_paths(self):
        from gitweave.transport import RecordingTransport

        def handler(method, url, **kwargs):
            return FakeResponse(method, url)

        transport = RecordingTransport(handler=handler)
        # simulate overlay apply create branch (5 calls: blobs×N, tree, commit, ref)
        transport.request("GET", "https://api.github.com/repos/org/repo/contents/.copier-answers.yml")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/blobs")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/trees")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/commits")
        transport.request("PATCH", "https://api.github.com/repos/org/repo/git/refs/heads/main")
        # simulate self-serve call
        transport.request("GET", "https://api.github.com/orgs/org/teams/team/memberships/user")
        # assert no PR opened
        transport.assert_no_pr_opens()

    def test_no_pr_mutant_detected(self):
        from gitweave.transport import RecordingTransport

        def handler(method, url, **kwargs):
            return FakeResponse(method, url)

        transport = RecordingTransport(handler=handler)
        transport.request("GET", "https://api.github.com/repos/org/repo/contents/.copier-answers.yml")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/blobs")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/trees")
        transport.request("POST", "https://api.github.com/repos/org/repo/git/commits")
        transport.request("PATCH", "https://api.github.com/repos/org/repo/git/refs/heads/main")
        # inject mutant: a PR open call
        transport.request("POST", "https://api.github.com/repos/org/repo/pulls")
        with self.assertRaises(AssertionError):
            transport.assert_no_pr_opens()


if __name__ == "__main__":
    unittest.main()
