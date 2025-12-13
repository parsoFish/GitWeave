import os
import unittest

class TestRepoStructure(unittest.TestCase):
    def setUp(self):
        # Assumes the test is run from the repo root or tests/ directory
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def test_root_directories_exist(self):
        """FR-001, FR-002, FR-006, FR-008: Verify core directories exist."""
        required_dirs = [
            'modules',
            'config',
            'infra',
            'metrics',
            '.github/workflows'
        ]
        for d in required_dirs:
            path = os.path.join(self.repo_root, d)
            self.assertTrue(os.path.isdir(path), f"Directory missing: {d}")

    def test_required_files_exist(self):
        """FR-003, FR-005, FR-007: Verify core files exist."""
        required_files = [
            'README.md',
            '.github/workflows/gitweave-apply.yaml',
            '.github/workflows/gitweave-infra.yaml',
            'infra/main.tf',
            'metrics/src/main.py'
        ]
        for f in required_files:
            path = os.path.join(self.repo_root, f)
            self.assertTrue(os.path.isfile(path), f"File missing: {f}")

if __name__ == '__main__':
    unittest.main()
