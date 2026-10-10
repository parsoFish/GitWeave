import os
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestPrunedArtefacts(unittest.TestCase):
    def _path(self, rel):
        return os.path.join(REPO_ROOT, rel)

    def test_metrics_directory_removed(self):
        self.assertFalse(
            os.path.isdir(self._path("metrics")),
            "metrics/ must be deleted in I1"
        )

    def test_example_template_module_removed(self):
        self.assertFalse(
            os.path.isdir(self._path("modules/example-template")),
            "modules/example-template/ must be deleted in I1"
        )

    def test_generate_update_pr_script_removed(self):
        self.assertFalse(
            os.path.isfile(self._path("scripts/generate-update-pr.py")),
            "scripts/generate-update-pr.py must be deleted in I1"
        )

    def test_test_modules_directory_removed(self):
        self.assertFalse(
            os.path.isdir(self._path("tests/test_modules")),
            "tests/test_modules/ must be deleted in I1"
        )

    def test_metrics_workflows_removed(self):
        for rel in (
            ".github/workflows/metrics-ci.yaml",
            ".github/workflows/metrics-docker.yaml",
        ):
            self.assertFalse(
                os.path.isfile(self._path(rel)),
                f"{rel} must be deleted in I1"
            )

    def test_retiring_test_files_removed(self):
        retiring = [
            "tests/test_demo_guide.py",
            "tests/test_stale_remote_branches.py",
            "tests/test_bootstrap_expand.py",
            "tests/test_dora_metrics_ci_workflow.py",
            "tests/test_metrics_dockerfile.py",
            "tests/test_metrics_docker_workflow.py",
        ]
        for rel in retiring:
            self.assertFalse(
                os.path.isfile(self._path(rel)),
                f"{rel} must be deleted in I1"
            )


if __name__ == "__main__":
    unittest.main()
