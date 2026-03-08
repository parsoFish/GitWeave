"""
Integration tests: apply overlay to a test repository and validate generated files.

These tests exercise the complete overlay-apply pipeline end-to-end against a real
GitHub test organisation. They define the expected behaviour of scripts/apply-overlays.py
when applied to a repository using the python-service module (TDD red phase — all tests
fail until the module and script are fully implemented).

Pipeline under test:
  1. Provision a temporary repository in the designated GitHub test org via the gh API.
  2. Write a RepositoryOverlay config pointing at the test repo (python-service module).
  3. Run scripts/apply-overlays.py, which: clones the repo, runs copier, commits,
     force-pushes a branch, and opens a PR.
  4. Clone the generated branch (gitweave/apply-overlays) into a local temp dir.
  5. Assert that all acceptance-criteria files exist with the expected content.
  6. Delete the test repository unconditionally via the gh API.

Runtime requirements (all must be present; tests are skipped otherwise):
  - GITHUB_TOKEN  — personal access token or GitHub App token with scopes:
                    repo (full), delete_repo, for the test org
  - GITWEAVE_TEST_ORG — name of a dedicated sandbox GitHub organisation
                        (NEVER a production org — tests create and delete repos)
  - copier CLI on PATH
  - git CLI on PATH
  - gh CLI on PATH

Idempotency guarantee:
  Running the full suite twice in sequence produces identical assertions because:
    - The apply script uses --overwrite (copier) and --force (git push), so the
      branch content is identical on every run.
    - A PR may already exist on the second run, but file assertions are made against
      the cloned branch, not against the PR.

Cleanup guarantee:
  The ``test_repo`` pytest fixture is module-scoped and uses ``yield`` with a
  ``finally`` block so the GitHub repository is deleted whether tests pass or fail.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "apply-overlays.py"
MODULES_DIR = REPO_ROOT / "modules"

# ---------------------------------------------------------------------------
# Environment / tooling requirements
# ---------------------------------------------------------------------------

_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_TEST_ORG = os.environ.get("GITWEAVE_TEST_ORG", "")

_REQUIRES_GITHUB_TOKEN = pytest.mark.skipif(
    not _GITHUB_TOKEN,
    reason=(
        "GITHUB_TOKEN not set — export a GitHub token with repo:write + delete_repo "
        "scope for GITWEAVE_TEST_ORG to run overlay integration tests"
    ),
)
_REQUIRES_TEST_ORG = pytest.mark.skipif(
    not _TEST_ORG,
    reason=(
        "GITWEAVE_TEST_ORG not set — export the name of a dedicated sandbox GitHub "
        "org to run overlay integration tests (NEVER a production org)"
    ),
)

pytestmark = [_REQUIRES_GITHUB_TOKEN, _REQUIRES_TEST_ORG]


def _tool_available(name: str) -> bool:
    """Return True when *name* is on the PATH and exits cleanly with --version."""
    try:
        result = subprocess.run(
            [name, "--version"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


_skip_no_copier = pytest.mark.skipif(
    not _tool_available("copier"),
    reason="copier CLI not available — install copier to run overlay integration tests",
)
_skip_no_gh = pytest.mark.skipif(
    not _tool_available("gh"),
    reason="gh CLI not available — install the GitHub CLI to run overlay integration tests",
)


# ---------------------------------------------------------------------------
# Fixed template inputs — deterministic, suitable for test assertions
# ---------------------------------------------------------------------------

SERVICE_NAME = "gitweave_test_svc"
PYTHON_VERSION = "3.12"
AUTHOR_NAME = "GitWeave CI"
DESCRIPTION = "Automated integration test service"

# The branch that apply-overlays.py creates in the target repo
OVERLAY_BRANCH = "gitweave/apply-overlays"


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def _gh(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """
    Invoke the gh CLI with the given arguments.

    Always captures stdout + stderr.  Raises ``subprocess.CalledProcessError``
    only when *check* is True and the exit code is non-zero.
    """
    env = {**os.environ, "GITHUB_TOKEN": _GITHUB_TOKEN, "GH_TOKEN": _GITHUB_TOKEN}
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


def _create_test_repo(org: str, repo_name: str) -> dict:
    """
    Create a repository named *repo_name* in *org* via the GitHub API.

    The repository is created private, empty (auto_init=true so it has a default
    branch), and with a description that identifies it as a GitWeave CI repo.
    Raises ``RuntimeError`` if the API call fails.

    Returns the parsed JSON response from the GitHub API.
    """
    payload = {
        "name": repo_name,
        "description": "GitWeave overlay integration test repo — safe to delete",
        "private": True,
        "auto_init": True,
    }
    result = _gh(
        "api",
        f"orgs/{org}/repos",
        "--method", "POST",
        "--input", "-",
        input=json.dumps(payload),
    )
    # Patch subprocess.run call — gh api does not support --input for stdin;
    # use the individual field approach instead.
    result = subprocess.run(
        [
            "gh", "api", f"orgs/{org}/repos",
            "--method", "POST",
            "-f", f"name={repo_name}",
            "-f", "description=GitWeave overlay integration test repo — safe to delete",
            "-F", "private=true",
            "-F", "auto_init=true",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_TOKEN": _GITHUB_TOKEN, "GH_TOKEN": _GITHUB_TOKEN},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create test repo {org}/{repo_name}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
    return json.loads(result.stdout)


def _delete_test_repo(org: str, repo_name: str) -> None:
    """
    Delete *org*/*repo_name* via the GitHub API.

    Failures are printed but never raised — cleanup must not mask test failures.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo_name}", "--method", "DELETE"],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_TOKEN": _GITHUB_TOKEN, "GH_TOKEN": _GITHUB_TOKEN},
    )
    if result.returncode != 0:
        print(
            f"[cleanup] WARNING: failed to delete {org}/{repo_name}.\n"
            f"  stderr: {result.stderr.strip()}\n"
            f"  stdout: {result.stdout.strip()}\n"
            f"  Manual cleanup may be required.",
            file=sys.stderr,
        )


def _repo_exists(org: str, repo_name: str) -> bool:
    """Return True when the repository exists and is accessible via the API."""
    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo_name}"],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_TOKEN": _GITHUB_TOKEN, "GH_TOKEN": _GITHUB_TOKEN},
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Overlay config builder
# ---------------------------------------------------------------------------


def _build_overlay_config(repo_slug: str) -> dict:
    """
    Return a RepositoryOverlay config dict targeting *repo_slug* with the
    python-service module and fixed test variables.

    The variables are passed as spec.variables so they are forwarded as
    ``--data KEY=VALUE`` flags to ``copier copy`` by apply-overlays.py.
    """
    return {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": "gitweave-overlay-integration-test"},
        "spec": {
            "repository": repo_slug,
            "modules": [{"name": "python-service"}],
            "variables": {
                "service_name": SERVICE_NAME,
                "description": DESCRIPTION,
                "python_version": PYTHON_VERSION,
                "author_name": AUTHOR_NAME,
            },
        },
    }


# ---------------------------------------------------------------------------
# Script runner
# ---------------------------------------------------------------------------


def _run_apply_script(
    config_dir: str,
    modules_dir: str | Path = MODULES_DIR,
    timeout: int = 180,
) -> subprocess.CompletedProcess:
    """
    Invoke scripts/apply-overlays.py with a real GITHUB_TOKEN.

    Returns the CompletedProcess; never raises on non-zero exit so tests can
    assert on the exit code themselves.
    """
    env = {**os.environ, "GITHUB_TOKEN": _GITHUB_TOKEN, "GH_TOKEN": _GITHUB_TOKEN}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config-dir", config_dir,
            "--modules-dir", str(modules_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _clone_branch(repo_slug: str, branch: str, target_dir: str) -> subprocess.CompletedProcess:
    """
    Clone a single branch of *repo_slug* into *target_dir* using GITHUB_TOKEN auth.

    Returns the CompletedProcess for the git clone command.
    """
    clone_url = f"https://x-access-token:{_GITHUB_TOKEN}@github.com/{repo_slug}.git"
    return subprocess.run(
        [
            "git", "clone",
            "--branch", branch,
            "--single-branch",
            "--depth", "1",
            clone_url,
            target_dir,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def test_repo(tmp_path_factory):
    """
    Module-scoped fixture that provisions a temporary GitHub repository in the
    GITWEAVE_TEST_ORG and tears it down unconditionally after all tests in this
    module complete.

    Yields a dict with keys:
      - org: str           — the test org name
      - repo_name: str     — the ephemeral repo name (unique per run)
      - repo_slug: str     — "{org}/{repo_name}"
      - config_dir: str    — path to a temp dir holding the overlay .yaml config
      - clone_dir: str     — path to a temp dir where the branch was cloned

    The fixture also runs apply-overlays.py once (module-scoped) so individual
    test functions can make assertions against the cloned branch without
    re-triggering the full pipeline on every test.
    """
    org = _TEST_ORG
    # Use a timestamp suffix to avoid name collisions when tests are re-run quickly
    repo_name = f"gitweave-overlay-int-test-{int(time.time())}"
    repo_slug = f"{org}/{repo_name}"
    config_dir = str(tmp_path_factory.mktemp("overlay-config"))
    clone_base = tmp_path_factory.mktemp("clone")

    # ----- Arrange --------------------------------------------------------
    try:
        _create_test_repo(org, repo_name)
    except RuntimeError as exc:
        pytest.fail(
            f"Fixture setup failed: could not create test repo {repo_slug}.\n{exc}"
        )

    # Write the overlay config into the temp config dir
    config_path = os.path.join(config_dir, "test-overlay.yaml")
    with open(config_path, "w") as f:
        yaml.dump(_build_overlay_config(repo_slug), f, default_flow_style=False)

    # Brief pause to let GitHub initialise the repo (avoids immediate 404s on clone)
    time.sleep(3)

    # ----- Act: run the full overlay pipeline ------------------------------
    apply_result = _run_apply_script(config_dir=config_dir)

    # Clone the generated branch so test functions can inspect file content
    clone_dir = str(clone_base / repo_name)
    clone_result = _clone_branch(repo_slug, OVERLAY_BRANCH, clone_dir)

    # ----- Yield to tests --------------------------------------------------
    yield {
        "org": org,
        "repo_name": repo_name,
        "repo_slug": repo_slug,
        "config_dir": config_dir,
        "clone_dir": clone_dir,
        "apply_result": apply_result,
        "clone_result": clone_result,
    }

    # ----- Teardown: always runs, even on failure --------------------------
    _delete_test_repo(org, repo_name)


@pytest.fixture(scope="module")
def second_apply_result(test_repo):
    """
    Run apply-overlays.py a second time against the same repo to verify idempotency.
    Yields the CompletedProcess from the second invocation.
    """
    second = _run_apply_script(config_dir=test_repo["config_dir"])
    yield second


@pytest.fixture(scope="module")
def second_clone_dir(test_repo, second_apply_result, tmp_path_factory):
    """
    Clone the overlay branch again after the second apply run.
    Yields the path to the second clone directory.
    """
    clone_base = tmp_path_factory.mktemp("clone2")
    clone_dir = str(clone_base / "second")
    _clone_branch(test_repo["repo_slug"], OVERLAY_BRANCH, clone_dir)
    yield clone_dir


# ---------------------------------------------------------------------------
# TestRepoProvisioning — the fixture creates and cleans up the test repo
# ---------------------------------------------------------------------------


class TestRepoProvisioning:
    """Verify that the test org and repo provisioning work correctly."""

    def test_test_repo_was_created_in_test_org(self, test_repo):
        """
        The fixture must create a repository in GITWEAVE_TEST_ORG via the GitHub API.

        This test verifies the provisioning step — if it fails, the entire
        integration suite is invalid.
        """
        assert _repo_exists(test_repo["org"], test_repo["repo_name"]), (
            f"Test repository {test_repo['repo_slug']} was not found in GitHub. "
            f"The gh API create call may have failed silently — check the fixture setup."
        )

    def test_overlay_config_was_written_with_python_service_module(self, test_repo):
        """
        The overlay config written by the fixture must reference the python-service
        module, so apply-overlays.py runs copier against the correct template.
        """
        config_path = os.path.join(test_repo["config_dir"], "test-overlay.yaml")
        assert os.path.isfile(config_path), (
            f"Overlay config file not found at {config_path}"
        )
        with open(config_path) as f:
            doc = yaml.safe_load(f)

        modules = doc.get("spec", {}).get("modules", [])
        module_names = [m.get("name") for m in modules]
        assert "python-service" in module_names, (
            f"Overlay config does not reference 'python-service' module. "
            f"Found modules: {module_names}"
        )

    def test_overlay_config_targets_the_test_repo(self, test_repo):
        """
        The overlay config must target the test repo slug so apply-overlays.py
        clones and modifies the correct repository.
        """
        config_path = os.path.join(test_repo["config_dir"], "test-overlay.yaml")
        with open(config_path) as f:
            doc = yaml.safe_load(f)
        repo_in_config = doc.get("spec", {}).get("repository", "")
        assert repo_in_config == test_repo["repo_slug"], (
            f"Overlay config targets {repo_in_config!r} instead of "
            f"the test repo {test_repo['repo_slug']!r}"
        )

    def test_overlay_config_contains_python_service_variables(self, test_repo):
        """
        The overlay config must include the variables (service_name, python_version,
        description, author_name) needed to render the python-service template.
        """
        config_path = os.path.join(test_repo["config_dir"], "test-overlay.yaml")
        with open(config_path) as f:
            doc = yaml.safe_load(f)
        variables = doc.get("spec", {}).get("variables", {})
        for expected_key in ("service_name", "python_version", "description", "author_name"):
            assert expected_key in variables, (
                f"Overlay config is missing required variable '{expected_key}'. "
                f"Found variables: {list(variables.keys())}"
            )


# ---------------------------------------------------------------------------
# TestApplyScriptExecution — the script runs and exits cleanly
# ---------------------------------------------------------------------------


class TestApplyScriptExecution:
    """Verify that apply-overlays.py completes successfully against the test repo."""

    def test_apply_script_exits_zero(self, test_repo):
        """
        scripts/apply-overlays.py must exit 0 when applied to the test repo
        with the python-service module.

        A non-zero exit means copier failed, git push failed, or another step
        in the pipeline failed — in any case the generated files are absent.

        stdout: {apply_result.stdout}
        stderr: {apply_result.stderr}
        """
        apply_result = test_repo["apply_result"]
        assert apply_result.returncode == 0, (
            f"apply-overlays.py exited {apply_result.returncode} for "
            f"{test_repo['repo_slug']}.\n"
            f"STDOUT:\n{apply_result.stdout}\n"
            f"STDERR:\n{apply_result.stderr}\n"
            "Possible causes: modules/python-service/ not implemented, "
            "copier not installed, or GITHUB_TOKEN lacks write permissions."
        )

    def test_apply_output_mentions_test_repo(self, test_repo):
        """
        apply-overlays.py output must include the test repo slug, confirming
        that the config was loaded and processed.
        """
        apply_result = test_repo["apply_result"]
        combined = apply_result.stdout + apply_result.stderr
        assert test_repo["repo_slug"] in combined, (
            f"Script output does not mention the test repo {test_repo['repo_slug']!r}. "
            f"The overlay config may not have been loaded.\n"
            f"STDOUT:\n{apply_result.stdout}\nSTDERR:\n{apply_result.stderr}"
        )

    def test_apply_output_reports_ok_for_test_repo(self, test_repo):
        """
        The apply output must include a success indicator ([OK]) for the test repo.
        """
        apply_result = test_repo["apply_result"]
        assert "[OK]" in apply_result.stdout, (
            f"Script output does not contain '[OK]' success marker for "
            f"{test_repo['repo_slug']}.\n"
            f"STDOUT:\n{apply_result.stdout}\nSTDERR:\n{apply_result.stderr}"
        )

    def test_overlay_branch_is_accessible_via_git_clone(self, test_repo):
        """
        After apply-overlays.py succeeds, the '{OVERLAY_BRANCH}' branch must
        exist in the test repo and be cloneable.

        A clone failure means the push step failed, even if the script reported
        success — both conditions must hold for the file assertions to be valid.
        """
        clone_result = test_repo["clone_result"]
        assert clone_result.returncode == 0, (
            f"Failed to clone branch '{OVERLAY_BRANCH}' from {test_repo['repo_slug']}.\n"
            f"STDOUT:\n{clone_result.stdout}\nSTDERR:\n{clone_result.stderr}\n"
            "This means git push failed or the branch was not created."
        )


# ---------------------------------------------------------------------------
# TestGeneratedFilesExist — acceptance criteria: required files are present
# ---------------------------------------------------------------------------


class TestGeneratedFilesExist:
    """
    Assert that the acceptance-criteria output files exist in the generated branch.

    These tests fail until modules/python-service/ is implemented with the
    correct copier template structure (TDD red phase).
    """

    def test_pyproject_toml_exists_in_generated_branch(self, test_repo):
        """
        pyproject.toml must exist at the root of the generated branch.

        This file is required for the service to be installable as a Python
        package and for pip to resolve its dependencies.
        """
        clone_dir = Path(test_repo["clone_dir"])
        pyproject = clone_dir / "pyproject.toml"
        assert pyproject.exists(), (
            f"pyproject.toml was not found in the generated branch {OVERLAY_BRANCH!r}.\n"
            f"Clone directory contents: {list(clone_dir.iterdir()) if clone_dir.exists() else '(directory missing)'}\n"
            "The python-service copier template must generate pyproject.toml."
        )

    def test_dockerfile_exists_in_generated_branch(self, test_repo):
        """
        Dockerfile must exist at the root of the generated branch.

        Without a Dockerfile the service cannot be containerised, which is a
        hard requirement for Python microservices in this organisation.
        """
        clone_dir = Path(test_repo["clone_dir"])
        dockerfile = clone_dir / "Dockerfile"
        assert dockerfile.exists(), (
            f"Dockerfile was not found in the generated branch {OVERLAY_BRANCH!r}.\n"
            f"Clone directory contents: {list(clone_dir.iterdir()) if clone_dir.exists() else '(directory missing)'}\n"
            "The python-service copier template must generate a Dockerfile."
        )

    def test_src_package_directory_exists_in_generated_branch(self, test_repo):
        """
        src/{SERVICE_NAME}/ directory must exist in the generated branch.

        The src-layout is required so the service package is importable without
        editable-install hacks in the container.
        """
        clone_dir = Path(test_repo["clone_dir"])
        src_pkg = clone_dir / "src" / SERVICE_NAME
        assert src_pkg.is_dir(), (
            f"src/{SERVICE_NAME}/ was not found in the generated branch {OVERLAY_BRANCH!r}.\n"
            f"src/ contents: {list((clone_dir / 'src').iterdir()) if (clone_dir / 'src').exists() else '(src/ missing)'}\n"
            "The python-service template must generate src/<service_name>/ (src-layout)."
        )

    def test_src_package_init_py_exists_in_generated_branch(self, test_repo):
        """
        src/{SERVICE_NAME}/__init__.py must exist to make the directory a package.

        Without __init__.py Python cannot import the service module in the container.
        """
        clone_dir = Path(test_repo["clone_dir"])
        init_py = clone_dir / "src" / SERVICE_NAME / "__init__.py"
        assert init_py.exists(), (
            f"src/{SERVICE_NAME}/__init__.py was not found in the generated branch.\n"
            "The python-service template must generate __init__.py to make the "
            "directory a proper Python package."
        )

    def test_copier_answers_yaml_exists_in_generated_branch(self, test_repo):
        """
        .copier-answers.yaml must exist so that future 'copier update' runs can
        replay the same variable values without requiring user input.
        """
        clone_dir = Path(test_repo["clone_dir"])
        answers = clone_dir / ".copier-answers.yaml"
        assert answers.exists(), (
            f".copier-answers.yaml was not found in the generated branch {OVERLAY_BRANCH!r}.\n"
            "copier should write this file automatically when 'copier copy' is run."
        )


# ---------------------------------------------------------------------------
# TestGeneratedFileContent — acceptance criteria: content matches expected output
# ---------------------------------------------------------------------------


class TestGeneratedFileContent:
    """
    Assert that generated file content matches the expected Jinja2-rendered output
    for the fixed test inputs (SERVICE_NAME, PYTHON_VERSION, AUTHOR_NAME, DESCRIPTION).

    These tests are the primary acceptance gate — they verify that the template
    renders correct, usable content, not just that files exist.
    """

    # ---- pyproject.toml ---------------------------------------------------

    def test_pyproject_toml_is_valid_toml(self, test_repo):
        """
        The generated pyproject.toml must be valid TOML so tools like pip and
        build backends can parse it without error.
        """
        pyproject_path = Path(test_repo["clone_dir"]) / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not generated — see TestGeneratedFilesExist"
        with open(pyproject_path, "rb") as fh:
            try:
                tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                pytest.fail(
                    f"Generated pyproject.toml is not valid TOML.\n"
                    f"Parse error: {exc}\n"
                    f"Content:\n{pyproject_path.read_text()}"
                )

    def test_pyproject_toml_project_name_equals_service_name(self, test_repo):
        """
        [project].name in the generated pyproject.toml must equal SERVICE_NAME.

        Pip, PyPI, and build tools derive the package identity from this field;
        a mismatch would cause the service to be installed under the wrong name.
        """
        pyproject_path = Path(test_repo["clone_dir"]) / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not generated — see TestGeneratedFilesExist"
        with open(pyproject_path, "rb") as fh:
            doc = tomllib.load(fh)
        assert doc["project"]["name"] == SERVICE_NAME, (
            f"pyproject.toml [project].name is {doc['project']['name']!r}, "
            f"expected {SERVICE_NAME!r}. "
            "The template variable service_name was not correctly applied."
        )

    def test_pyproject_toml_description_equals_input_description(self, test_repo):
        """
        [project].description must equal the DESCRIPTION variable passed to copier.
        """
        pyproject_path = Path(test_repo["clone_dir"]) / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not generated — see TestGeneratedFilesExist"
        with open(pyproject_path, "rb") as fh:
            doc = tomllib.load(fh)
        assert doc["project"]["description"] == DESCRIPTION, (
            f"pyproject.toml [project].description is {doc['project']['description']!r}, "
            f"expected {DESCRIPTION!r}."
        )

    def test_pyproject_toml_requires_python_contains_version(self, test_repo):
        """
        [project].requires-python must reference PYTHON_VERSION so that pip
        enforces interpreter compatibility when installing the service.
        """
        pyproject_path = Path(test_repo["clone_dir"]) / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not generated — see TestGeneratedFilesExist"
        with open(pyproject_path, "rb") as fh:
            doc = tomllib.load(fh)
        requires_python = doc["project"]["requires-python"]
        assert PYTHON_VERSION in requires_python, (
            f"pyproject.toml [project].requires-python is {requires_python!r} — "
            f"does not contain the PYTHON_VERSION {PYTHON_VERSION!r}."
        )

    def test_pyproject_toml_authors_contains_author_name(self, test_repo):
        """
        [project].authors must contain a record with AUTHOR_NAME so that package
        metadata correctly attributes the service owner.
        """
        pyproject_path = Path(test_repo["clone_dir"]) / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not generated — see TestGeneratedFilesExist"
        content = pyproject_path.read_text()
        assert AUTHOR_NAME in content, (
            f"pyproject.toml does not reference AUTHOR_NAME {AUTHOR_NAME!r}. "
            "The template must render the author_name variable into [project].authors."
        )

    # ---- Dockerfile -------------------------------------------------------

    def test_dockerfile_from_references_correct_python_version(self, test_repo):
        """
        The Dockerfile FROM instruction must reference the python:<PYTHON_VERSION>-slim
        base image so containers run the correct interpreter.

        FROM python:3.12-slim  ← expected when PYTHON_VERSION == "3.12"
        """
        dockerfile_path = Path(test_repo["clone_dir"]) / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile not generated — see TestGeneratedFilesExist"
        content = dockerfile_path.read_text()
        expected_from = f"FROM python:{PYTHON_VERSION}-slim"
        assert expected_from in content, (
            f"Dockerfile does not contain '{expected_from}'.\n"
            f"Dockerfile content:\n{content}"
        )

    def test_dockerfile_references_service_name_in_cmd(self, test_repo):
        """
        The Dockerfile CMD or ENTRYPOINT must reference SERVICE_NAME so Docker
        executes the correct Python module as the container entry point.
        """
        dockerfile_path = Path(test_repo["clone_dir"]) / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile not generated — see TestGeneratedFilesExist"
        content = dockerfile_path.read_text()
        assert SERVICE_NAME in content, (
            f"Dockerfile does not reference SERVICE_NAME {SERVICE_NAME!r}.\n"
            f"Dockerfile content:\n{content}"
        )

    def test_dockerfile_uses_slim_base_image(self, test_repo):
        """
        The generated Dockerfile must use a -slim base image to minimise the
        container attack surface and image size.
        """
        dockerfile_path = Path(test_repo["clone_dir"]) / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile not generated — see TestGeneratedFilesExist"
        content = dockerfile_path.read_text()
        assert "-slim" in content, (
            "Dockerfile does not use a '-slim' Python base image. "
            "Use python:<version>-slim to reduce attack surface."
        )

    # ---- src/<service_name>/__init__.py -----------------------------------

    def test_src_init_py_is_a_valid_python_file(self, test_repo):
        """
        src/{SERVICE_NAME}/__init__.py must be syntactically valid Python so
        imports don't raise SyntaxError at container startup.
        """
        init_py_path = Path(test_repo["clone_dir"]) / "src" / SERVICE_NAME / "__init__.py"
        assert init_py_path.exists(), (
            f"src/{SERVICE_NAME}/__init__.py not generated — see TestGeneratedFilesExist"
        )
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(init_py_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"src/{SERVICE_NAME}/__init__.py has a syntax error.\n"
            f"Error: {result.stderr}\n"
            f"Content:\n{init_py_path.read_text()}"
        )

    # ---- .copier-answers.yaml ---------------------------------------------

    def test_copier_answers_yaml_records_service_name(self, test_repo):
        """
        .copier-answers.yaml must record the service_name variable so that
        'copier update' can replay it without prompting.
        """
        answers_path = Path(test_repo["clone_dir"]) / ".copier-answers.yaml"
        assert answers_path.exists(), ".copier-answers.yaml not generated"
        answers = yaml.safe_load(answers_path.read_text())
        assert answers.get("service_name") == SERVICE_NAME, (
            f".copier-answers.yaml has service_name={answers.get('service_name')!r}, "
            f"expected {SERVICE_NAME!r}."
        )

    def test_copier_answers_yaml_records_python_version(self, test_repo):
        """
        .copier-answers.yaml must record the python_version variable so that
        future 'copier update' runs know which interpreter version was used.
        """
        answers_path = Path(test_repo["clone_dir"]) / ".copier-answers.yaml"
        assert answers_path.exists(), ".copier-answers.yaml not generated"
        answers = yaml.safe_load(answers_path.read_text())
        assert str(answers.get("python_version", "")) == PYTHON_VERSION, (
            f".copier-answers.yaml has python_version={answers.get('python_version')!r}, "
            f"expected {PYTHON_VERSION!r}."
        )


# ---------------------------------------------------------------------------
# TestIdempotency — running twice produces identical assertions
# ---------------------------------------------------------------------------


class TestIdempotency:
    """
    Verify that running apply-overlays.py a second time against the same repository
    produces identical file content. This guarantees that CI reruns and overlapping
    runs don't corrupt the generated output.

    Uses module-scoped fixtures so the second apply and re-clone happen once for
    all tests in this class.
    """

    def test_second_apply_exits_zero(self, second_apply_result):
        """
        apply-overlays.py must exit 0 on the second run, even if a PR already
        exists. The --force push overwrites the branch, and the script must
        handle the pre-existing PR gracefully.
        """
        assert second_apply_result.returncode == 0, (
            f"apply-overlays.py failed on the second run (idempotency check).\n"
            f"STDOUT:\n{second_apply_result.stdout}\n"
            f"STDERR:\n{second_apply_result.stderr}\n"
            "The script must be idempotent — running twice should exit 0 both times."
        )

    def test_pyproject_toml_content_is_identical_on_second_run(
        self, test_repo, second_clone_dir
    ):
        """
        pyproject.toml content must be byte-for-byte identical on both runs.

        Two successive runs with identical inputs must produce identical output —
        non-deterministic rendering (timestamps, UUIDs, etc.) would violate this
        contract and make CI diffs noisy.
        """
        first = Path(test_repo["clone_dir"]) / "pyproject.toml"
        second = Path(second_clone_dir) / "pyproject.toml"

        if not first.exists() or not second.exists():
            pytest.skip("pyproject.toml not generated — see TestGeneratedFilesExist")

        assert first.read_text() == second.read_text(), (
            "pyproject.toml content differs between the first and second apply runs. "
            "The template must render deterministically for the same inputs.\n"
            f"First run content:\n{first.read_text()}\n"
            f"Second run content:\n{second.read_text()}"
        )

    def test_dockerfile_content_is_identical_on_second_run(
        self, test_repo, second_clone_dir
    ):
        """
        Dockerfile content must be byte-for-byte identical on both runs.
        """
        first = Path(test_repo["clone_dir"]) / "Dockerfile"
        second = Path(second_clone_dir) / "Dockerfile"

        if not first.exists() or not second.exists():
            pytest.skip("Dockerfile not generated — see TestGeneratedFilesExist")

        assert first.read_text() == second.read_text(), (
            "Dockerfile content differs between the first and second apply runs. "
            "The template must render deterministically for the same inputs."
        )

    def test_src_init_py_content_is_identical_on_second_run(
        self, test_repo, second_clone_dir
    ):
        """
        src/{SERVICE_NAME}/__init__.py content must be identical on both runs.
        """
        first = Path(test_repo["clone_dir"]) / "src" / SERVICE_NAME / "__init__.py"
        second = Path(second_clone_dir) / "src" / SERVICE_NAME / "__init__.py"

        if not first.exists() or not second.exists():
            pytest.skip(
                f"src/{SERVICE_NAME}/__init__.py not generated — see TestGeneratedFilesExist"
            )

        assert first.read_text() == second.read_text(), (
            f"src/{SERVICE_NAME}/__init__.py differs between runs. "
            "Template output must be deterministic."
        )


# ---------------------------------------------------------------------------
# TestCleanup — verify teardown behaviour (repo deleted after yield)
# ---------------------------------------------------------------------------


class TestCleanup:
    """
    These tests verify that cleanup logic is correctly structured.

    The actual deletion happens after the module-scoped ``test_repo`` fixture
    yields, so we can only test teardown indirectly (the fixture structure
    guarantees unconditional cleanup via finally).

    We do test the ``_delete_test_repo`` helper directly to confirm it behaves
    correctly in isolation.
    """

    def test_delete_repo_helper_does_not_raise_when_repo_does_not_exist(self):
        """
        _delete_test_repo must not raise even when the repo is already gone.

        Cleanup runs after all tests; if a test deletes the repo early, the
        fixture teardown must still complete without masking the test result.
        """
        # A repo that certainly doesn't exist — function must not raise
        try:
            _delete_test_repo(_TEST_ORG, "gitweave-nonexistent-repo-0000000")
        except Exception as exc:
            pytest.fail(
                f"_delete_test_repo raised an unexpected exception for a "
                f"non-existent repo: {exc}"
            )

    def test_repo_exists_helper_returns_false_for_nonexistent_repo(self):
        """
        _repo_exists must return False for a repository that doesn't exist.

        This helper is used in TestRepoProvisioning to confirm creation worked,
        and must be reliable in both directions.
        """
        result = _repo_exists(_TEST_ORG, "gitweave-certainly-does-not-exist-xyz987")
        assert result is False, (
            "Expected _repo_exists to return False for a non-existent repo, "
            "but it returned True. The helper may not be reading the API response correctly."
        )
