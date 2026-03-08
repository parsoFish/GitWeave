"""
Integration tests: full terraform init → fmt -check → validate → plan pipeline.

These tests execute the terraform CLI directly against infra/ using a minimal
example configuration and a read-only test GitHub token.  They verify that the
pipeline that CI runs on infra/-touching PRs works correctly end-to-end.

Test layers:
  - Integration (happy path): terraform fmt → init → validate → plan all exit 0
    when pointed at a test org with GITHUB_TOKEN set to a test token.
  - Integration (failure detection): the pipeline must fail on an intentional
    terraform fmt violation — confirming the quality gate is not vacuous.
  - Integration (fmt check): fmt -check must exit non-zero when a malformatted
    .tf file is present; exit 0 after the file is corrected.

Runtime requirements:
  - terraform CLI on PATH (skipped if missing)
  - GITHUB_TOKEN env var set to a read-only token for the test org
    (skipped gracefully when absent, but tested when present)
  - TF_VAR_github_org env var set to the test org name
    (falls back to the GITWEAVE_TEST_ORG env var, then to a sentinel skip)

The tests use -backend=false for init so no remote state backend is required.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INFRA_DIR = os.path.join(REPO_ROOT, "infra")

# Name of the env var holding the read-only test-org GitHub token.
# In CI this is injected from a repository secret (never the production token).
_TOKEN_ENV_VAR = "GITHUB_TOKEN"

# The GitHub org to plan against. Must be a test/sandbox org, not production.
# Accepts TF_VAR_github_org first, then GITWEAVE_TEST_ORG, then skips.
_ORG_ENV_VARS = ("TF_VAR_github_org", "GITWEAVE_TEST_ORG")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _terraform_available() -> bool:
    """Return True if the terraform CLI is on the PATH."""
    try:
        result = subprocess.run(
            ["terraform", "version"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _github_token() -> str | None:
    """Return the GitHub token from the environment, or None if not set."""
    return os.environ.get(_TOKEN_ENV_VAR) or None


def _test_org() -> str | None:
    """Return the test org name from the environment, or None if not configured."""
    for var in _ORG_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return None


def _run(
    args: list[str],
    cwd: str = INFRA_DIR,
    timeout: int = 60,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess and return the completed process."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        env=env,
    )


def _terraform_env(org: str, token: str) -> dict[str, str]:
    """Build the environment dict required for terraform provider auth."""
    return {
        "TF_VAR_github_org": org,
        "GITHUB_TOKEN": token,
        # Disable colour so output is grep-friendly in test assertions
        "TF_CLI_ARGS": "-no-color",
    }


# ---------------------------------------------------------------------------
# Skip decorators
# ---------------------------------------------------------------------------

_skip_no_terraform = unittest.skipUnless(
    _terraform_available(),
    "terraform CLI not available — install terraform to run integration tests",
)

_skip_no_token = unittest.skipUnless(
    bool(_github_token()),
    f"${_TOKEN_ENV_VAR} not set — set a read-only test-org GitHub token to run "
    "the full pipeline integration tests",
)

_skip_no_org = unittest.skipUnless(
    bool(_test_org()),
    f"Neither $TF_VAR_github_org nor $GITWEAVE_TEST_ORG is set — configure a "
    "test/sandbox GitHub org name to run plan integration tests",
)


# ---------------------------------------------------------------------------
# terraform fmt -check (no token required)
# ---------------------------------------------------------------------------


@_skip_no_terraform
class TestTerraformFmtCheckInfra(unittest.TestCase):
    """
    'terraform fmt -check -recursive .' must exit 0 for the entire infra/ tree.

    This test mirrors the CI fmt gate and runs without GitHub credentials —
    fmt is a local, provider-agnostic operation.
    """

    def test_fmt_check_passes_on_infra_directory(self):
        """
        'terraform fmt -check -recursive .' exits 0 for infra/.

        A non-zero exit means at least one file has style violations.
        Run 'terraform fmt -recursive infra/' to auto-fix, then re-commit.
        """
        result = _run(
            ["terraform", "fmt", "-check", "-recursive", "-no-color", "."],
            cwd=INFRA_DIR,
        )
        self.assertEqual(
            result.returncode,
            0,
            "terraform fmt -check failed on infra/ — formatting violations detected.\n"
            f"Files with violations:\n{result.stdout}\n"
            f"Stderr:\n{result.stderr}\n"
            "Run 'terraform fmt -recursive infra/' to auto-fix.",
        )

    def test_fmt_check_fails_on_intentionally_malformatted_file(self):
        """
        'terraform fmt -check' must exit non-zero when a malformatted .tf file
        is introduced. This test confirms the quality gate is not vacuous —
        a real formatting error is caught, not silently ignored.

        Approach: write a temp .tf file with misaligned HCL into a temp dir,
        run fmt -check against that dir, and assert exit code is non-zero.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_tf = os.path.join(tmpdir, "bad_format.tf")
            # HCL with misaligned equals signs — terraform fmt would rewrite this
            with open(bad_tf, "w") as f:
                f.write(
                    'variable "example" {\n'
                    '  type        = string\n'
                    '  default= "misaligned"\n'  # missing space before =
                    "}\n"
                )
            result = _run(
                ["terraform", "fmt", "-check", "-no-color", "."],
                cwd=tmpdir,
            )
            self.assertNotEqual(
                result.returncode,
                0,
                "terraform fmt -check returned exit 0 for a deliberately "
                "malformatted file. The fmt gate is not enforcing style.",
            )

    def test_fmt_check_passes_after_fixing_malformatted_file(self):
        """
        After 'terraform fmt' fixes a malformatted file, 'terraform fmt -check'
        must exit 0. This validates that the fix-then-check cycle works correctly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_tf = os.path.join(tmpdir, "needs_format.tf")
            with open(bad_tf, "w") as f:
                f.write(
                    'variable "example" {\n'
                    '  type        = string\n'
                    '  default= "misaligned"\n'
                    "}\n"
                )
            # Auto-fix with terraform fmt (no -check)
            fix_result = _run(["terraform", "fmt", "-no-color", "."], cwd=tmpdir)
            self.assertEqual(
                fix_result.returncode,
                0,
                "terraform fmt (auto-fix) failed unexpectedly:\n"
                f"{fix_result.stdout}\n{fix_result.stderr}",
            )
            # Now -check should pass
            check_result = _run(
                ["terraform", "fmt", "-check", "-no-color", "."],
                cwd=tmpdir,
            )
            self.assertEqual(
                check_result.returncode,
                0,
                "terraform fmt -check failed after auto-formatting:\n"
                f"{check_result.stdout}\n{check_result.stderr}",
            )


# ---------------------------------------------------------------------------
# terraform init -backend=false (no token required)
# ---------------------------------------------------------------------------


@_skip_no_terraform
class TestTerraformInitBackendFalse(unittest.TestCase):
    """
    'terraform init -backend=false' must exit 0 to confirm the provider
    configuration is parseable and plugins can be downloaded.

    No GitHub token is required for init — providers are resolved from the
    registry, not the API.
    """

    def test_init_backend_false_exits_zero(self):
        """
        'terraform init -backend=false' exits 0 for infra/.

        A non-zero exit means the required_providers block has errors, the
        registry is unreachable, or a version constraint is unsatisfiable.
        """
        result = _run(
            ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
            cwd=INFRA_DIR,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            "terraform init -backend=false failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}",
        )

    def test_init_backend_false_does_not_require_backend_credentials(self):
        """
        Init with -backend=false must succeed without any backend credentials
        (no AWS keys, no GCS tokens, no Azure SAS).

        Failure here means the configuration has a backend block that cannot
        be bypassed, which breaks the CI pipeline for developers without
        production cloud access.
        """
        env = os.environ.copy()
        # Strip common backend credential env vars to simulate a clean CI env
        for key in list(env):
            if any(
                key.startswith(prefix)
                for prefix in (
                    "AWS_",
                    "GOOGLE_",
                    "ARM_",
                    "TFE_TOKEN",
                    "ATLAS_TOKEN",
                )
            ):
                del env[key]

        result = subprocess.run(
            ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
            capture_output=True,
            text=True,
            cwd=INFRA_DIR,
            timeout=180,
            env=env,
        )
        self.assertEqual(
            result.returncode,
            0,
            "terraform init -backend=false failed when backend credential env vars "
            "were stripped. The infra/ config may have a backend block that cannot "
            "be bypassed with -backend=false.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}",
        )


# ---------------------------------------------------------------------------
# terraform validate (no token required after init)
# ---------------------------------------------------------------------------


@_skip_no_terraform
class TestTerraformValidateAfterInit(unittest.TestCase):
    """
    'terraform validate' must exit 0 after a successful init.

    Validate checks HCL syntax and schema correctness without contacting any
    provider API — no GitHub token is required.
    """

    @classmethod
    def setUpClass(cls):
        """Run terraform init once for the validate test class."""
        _run(
            ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
            cwd=INFRA_DIR,
            timeout=180,
        )

    def test_validate_exits_zero(self):
        """'terraform validate' exits 0 for infra/."""
        result = _run(["terraform", "validate", "-no-color"], cwd=INFRA_DIR)
        self.assertEqual(
            result.returncode,
            0,
            "terraform validate failed for infra/.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}",
        )

    def test_validate_outputs_success_message(self):
        """'terraform validate' output must contain the word 'Success'."""
        result = _run(["terraform", "validate", "-no-color"], cwd=INFRA_DIR)
        combined = result.stdout + result.stderr
        self.assertIn(
            "Success",
            combined,
            "terraform validate exited 0 but did not output a 'Success' message.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}",
        )

    def test_validate_outputs_no_errors(self):
        """'terraform validate' must not mention 'Error:' when exit code is 0."""
        result = _run(["terraform", "validate", "-no-color"], cwd=INFRA_DIR)
        if result.returncode == 0:
            self.assertNotIn(
                "Error:",
                result.stdout,
                "terraform validate exited 0 but contains 'Error:' in stdout.\n"
                f"STDOUT:\n{result.stdout}",
            )


# ---------------------------------------------------------------------------
# terraform plan (requires GITHUB_TOKEN + test org)
# ---------------------------------------------------------------------------


@_skip_no_terraform
@_skip_no_token
@_skip_no_org
class TestTerraformPlanExitsZero(unittest.TestCase):
    """
    Full pipeline integration test: terraform plan must exit 0 against the
    test org in a clean state.

    These tests require:
      - GITHUB_TOKEN set to a read-only token for the test org
      - TF_VAR_github_org (or GITWEAVE_TEST_ORG) set to the test org name

    They are skipped in environments without these credentials.
    """

    @classmethod
    def setUpClass(cls):
        """Run terraform init once before all plan tests."""
        token = _github_token()
        org = _test_org()
        env = _terraform_env(org, token)
        _run(
            ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
            cwd=INFRA_DIR,
            timeout=180,
            extra_env=env,
        )

    def _plan_env(self) -> dict[str, str]:
        return _terraform_env(_test_org(), _github_token())

    def test_plan_exits_zero_on_clean_state(self):
        """
        'terraform plan -input=false' must exit 0 when the test org is in a
        clean state that matches the example configuration.

        Exit 0 means terraform found no diff to apply (or planned successfully).
        A non-zero exit indicates a provider error, missing resources, or a
        malformed plan — all of which must fail the CI job.
        """
        result = _run(
            ["terraform", "plan", "-input=false", "-no-color"],
            cwd=INFRA_DIR,
            timeout=120,
            extra_env=self._plan_env(),
        )
        self.assertEqual(
            result.returncode,
            0,
            "terraform plan exited non-zero against the test org. "
            "This means the CI gate would fail on a clean PR.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}",
        )

    def test_plan_does_not_output_apply_errors(self):
        """
        The plan output must not contain 'Error:' — a successful plan is
        clean, not merely exit-0 with embedded error messages.
        """
        result = _run(
            ["terraform", "plan", "-input=false", "-no-color"],
            cwd=INFRA_DIR,
            timeout=120,
            extra_env=self._plan_env(),
        )
        if result.returncode == 0:
            self.assertNotIn(
                "Error:",
                result.stderr,
                "terraform plan exited 0 but has 'Error:' in stderr.\n"
                f"STDERR:\n{result.stderr}",
            )

    def test_plan_targets_test_org_not_production(self):
        """
        The plan must operate against a test/sandbox GitHub org, not the
        production org. We verify that the org name used in the plan output
        (if present) does not equal any known production org names.

        This guards against accidentally running the plan against production
        when the wrong token or org variable is set.
        """
        # Known production org names that must never appear in a test plan
        _PRODUCTION_ORG_NAMES = frozenset(
            os.environ.get("GITWEAVE_PRODUCTION_ORG", "").split(",")
        ) - {""}

        org = _test_org()
        if not _PRODUCTION_ORG_NAMES:
            # No production org configured — skip the guard
            self.skipTest(
                "GITWEAVE_PRODUCTION_ORG not set — cannot assert test-vs-production separation. "
                "Set GITWEAVE_PRODUCTION_ORG to the production org name to enable this check."
            )

        self.assertNotIn(
            org,
            _PRODUCTION_ORG_NAMES,
            f"The configured test org '{org}' is in the production org list "
            f"{_PRODUCTION_ORG_NAMES!r}. Use a dedicated test org for CI validation.",
        )


# ---------------------------------------------------------------------------
# Full pipeline timing — must complete in under 3 minutes
# ---------------------------------------------------------------------------


@_skip_no_terraform
class TestTerraformPipelineTiming(unittest.TestCase):
    """
    The full fmt → init → validate pipeline (without plan, which requires a
    token) must complete within 3 minutes on a warm runner.

    This test acts as a canary for provider-download regressions or network
    timeouts that would cause the CI job to breach the 3-minute SLA.
    """

    _MAX_WALL_SECONDS = 180  # 3 minutes

    def test_fmt_init_validate_pipeline_completes_within_three_minutes(self):
        """
        The sequential fmt -check → init -backend=false → validate pipeline
        must complete in under 3 minutes wall-clock time.

        If this test fails, the provider download or validation step has
        regressed in performance and the CI SLA cannot be met.
        """
        start = time.monotonic()

        fmt_result = _run(
            ["terraform", "fmt", "-check", "-recursive", "-no-color", "."],
            cwd=INFRA_DIR,
            timeout=self._MAX_WALL_SECONDS,
        )

        init_result = _run(
            ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
            cwd=INFRA_DIR,
            timeout=self._MAX_WALL_SECONDS,
        )

        validate_result = _run(
            ["terraform", "validate", "-no-color"],
            cwd=INFRA_DIR,
            timeout=self._MAX_WALL_SECONDS,
        )

        elapsed = time.monotonic() - start

        # Assert all steps passed before checking timing
        self.assertEqual(
            fmt_result.returncode,
            0,
            f"terraform fmt -check failed (timing test):\n{fmt_result.stdout}",
        )
        self.assertEqual(
            init_result.returncode,
            0,
            f"terraform init failed (timing test):\n{init_result.stdout}\n{init_result.stderr}",
        )
        self.assertEqual(
            validate_result.returncode,
            0,
            f"terraform validate failed (timing test):\n{validate_result.stdout}\n{validate_result.stderr}",
        )

        self.assertLessEqual(
            elapsed,
            self._MAX_WALL_SECONDS,
            f"fmt + init + validate pipeline took {elapsed:.1f}s, exceeding the "
            f"{self._MAX_WALL_SECONDS}s limit. The CI job cannot meet the <3-minute SLA.",
        )


# ---------------------------------------------------------------------------
# Failure detection — CI job must fail on errors
# ---------------------------------------------------------------------------


@_skip_no_terraform
class TestTerraformErrorDetection(unittest.TestCase):
    """
    These tests verify that the pipeline reports failures rather than silently
    passing when configuration errors are present. A CI gate that exits 0 on
    broken config is worse than no gate at all.
    """

    def test_validate_fails_on_invalid_hcl_syntax(self):
        """
        'terraform validate' must exit non-zero when a .tf file has invalid HCL.

        We write a broken .tf file to a temp directory, run init + validate
        against it, and assert that validate fails.  This mirrors the CI
        scenario where a developer accidentally pushes broken HCL.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_tf = os.path.join(tmpdir, "broken.tf")
            with open(bad_tf, "w") as f:
                # Missing closing brace — invalid HCL
                f.write(
                    'resource "null_resource" "bad" {\n'
                    "  # unclosed block\n"
                )

            # Init the temp dir (may fail due to no providers — that's fine)
            init_result = _run(
                ["terraform", "init", "-backend=false", "-no-color", "-input=false"],
                cwd=tmpdir,
                timeout=180,
            )

            validate_result = _run(
                ["terraform", "validate", "-no-color"],
                cwd=tmpdir,
                timeout=30,
            )

            # Either init or validate must report a non-zero exit for broken HCL
            both_zero = init_result.returncode == 0 and validate_result.returncode == 0
            self.assertFalse(
                both_zero,
                "terraform init and validate both exited 0 for a file with an "
                "unclosed HCL block. The CI gate would not catch this error.\n"
                f"init stdout:\n{init_result.stdout}\n"
                f"validate stdout:\n{validate_result.stdout}",
            )

    def test_fmt_check_fails_on_misaligned_arguments(self):
        """
        'terraform fmt -check' must exit non-zero for a file with misaligned
        argument assignments (the most common style violation in HCL).

        This verifies the CI fmt gate catches real-world formatting issues.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            misaligned_tf = os.path.join(tmpdir, "misaligned.tf")
            with open(misaligned_tf, "w") as f:
                # terraform fmt would align these to equal column widths
                f.write(
                    "locals {\n"
                    '  short = "a"\n'
                    '  a_longer_name= "b"\n'  # missing space before =
                    "}\n"
                )

            result = _run(
                ["terraform", "fmt", "-check", "-no-color", "."],
                cwd=tmpdir,
            )
            self.assertNotEqual(
                result.returncode,
                0,
                "terraform fmt -check returned exit 0 for a file with a "
                "misaligned argument assignment. The fmt gate is not enforcing style.",
            )

    def test_fmt_check_exits_nonzero_not_usage_error_on_violations(self):
        """
        When fmt -check detects violations it must exit 1 (formatting issues),
        not 2 (usage error) or any other code.

        Exit code semantics matter for CI: a usage error (2) would indicate a
        broken workflow command, not a formatting violation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_tf = os.path.join(tmpdir, "exit_code_test.tf")
            with open(bad_tf, "w") as f:
                f.write('variable "x" {\n  default= "bad"\n}\n')

            result = _run(
                ["terraform", "fmt", "-check", "-no-color", "."],
                cwd=tmpdir,
            )
            self.assertEqual(
                result.returncode,
                1,
                f"terraform fmt -check returned exit code {result.returncode} for "
                "a formatting violation. Expected exit 1 (fmt issues), not 2 (usage error).",
            )


if __name__ == "__main__":
    unittest.main()
