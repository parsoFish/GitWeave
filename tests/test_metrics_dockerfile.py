"""
Tests for metrics/Dockerfile — verifies that the containerization scaffolding
added by PR #21 (feat/GitWeave-metrics-docker) is present and correctly
structured.

Acceptance criteria:
  - metrics/Dockerfile exists
  - Base image is python:3.12-slim (minimal image footprint)
  - A non-root user is created (UID 1001 or named 'metrics') for security compliance
  - curl is installed (required by HEALTHCHECK probe)
  - HEALTHCHECK directive is present
  - requirements.txt is copied before source code (layer-cache optimisation)
  - Port 8000 is exposed (FastAPI default)

All tests in this file FAIL until metrics/Dockerfile is created by merging
PR #21 (TDD red phase).
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCKERFILE_PATH = REPO_ROOT / "metrics" / "Dockerfile"


def _read_dockerfile() -> str:
    """Return the Dockerfile content or skip the test if missing."""
    import unittest

    if not DOCKERFILE_PATH.exists():
        raise unittest.SkipTest(
            f"metrics/Dockerfile not found at {DOCKERFILE_PATH}. "
            "Merge PR #21 (feat/GitWeave-metrics-docker) to create it."
        )
    return DOCKERFILE_PATH.read_text()


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


class TestDockerfileExists(unittest.TestCase):
    """metrics/Dockerfile must exist after PR #21 is merged."""

    def test_dockerfile_exists_in_metrics_directory(self):
        """metrics/Dockerfile must be present — created by PR #21."""
        self.assertTrue(
            DOCKERFILE_PATH.exists(),
            f"metrics/Dockerfile not found at {DOCKERFILE_PATH}. "
            "Merge PR #21 (feat/GitWeave-metrics-docker) to create it.",
        )

    def test_dockerfile_is_not_empty(self):
        """Dockerfile must have non-empty content."""
        content = _read_dockerfile()
        self.assertTrue(
            content.strip(),
            "metrics/Dockerfile must not be empty",
        )


# ---------------------------------------------------------------------------
# Base image
# ---------------------------------------------------------------------------


class TestDockerfileBaseImage(unittest.TestCase):
    """Dockerfile must use python:3.12-slim as the base image."""

    def test_base_image_is_python_312_slim(self):
        """FROM must reference python:3.12-slim for minimal image footprint."""
        content = _read_dockerfile()
        self.assertRegex(
            content,
            r"FROM\s+python:3\.12",
            "Dockerfile must use python:3.12 (or python:3.12-slim) as the base image",
        )

    def test_base_image_uses_slim_variant(self):
        """slim variant keeps the image small — full debian image is too large."""
        content = _read_dockerfile()
        from_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("FROM")
        ]
        self.assertTrue(
            any("slim" in line for line in from_lines),
            "Dockerfile base image must use the -slim variant (e.g. python:3.12-slim) "
            f"to keep image size small; FROM lines found: {from_lines}",
        )


# ---------------------------------------------------------------------------
# Non-root user (security compliance)
# ---------------------------------------------------------------------------


class TestDockerfileNonRootUser(unittest.TestCase):
    """Container must run as a non-root user for security compliance."""

    def test_non_root_user_is_created(self):
        """A dedicated non-root user must be created via RUN useradd/adduser."""
        content = _read_dockerfile()
        has_useradd = re.search(r"useradd|adduser", content)
        has_user_directive = re.search(r"^USER\s+\S+", content, re.MULTILINE)
        self.assertTrue(
            has_useradd or has_user_directive,
            "Dockerfile must create and/or set a non-root user via RUN useradd/adduser "
            "and/or a USER directive",
        )

    def test_user_directive_switches_to_non_root(self):
        """USER directive must be present to switch to the non-root user."""
        content = _read_dockerfile()
        user_directives = [
            line.strip() for line in content.splitlines()
            if line.strip().upper().startswith("USER")
        ]
        self.assertGreater(
            len(user_directives),
            0,
            "Dockerfile must have a USER directive to switch to the non-root user; "
            "running as root in production containers violates security policy",
        )
        # The final USER directive must not be 'root'
        final_user = user_directives[-1]
        self.assertNotRegex(
            final_user,
            r"(?i)USER\s+root$",
            f"Dockerfile must not end with USER root; found: {final_user!r}",
        )


# ---------------------------------------------------------------------------
# curl installation (required by HEALTHCHECK)
# ---------------------------------------------------------------------------


class TestDockerfileCurlInstalled(unittest.TestCase):
    """curl must be installed — it is used by the HEALTHCHECK CMD."""

    def test_curl_is_installed_in_dockerfile(self):
        """RUN apt-get install must include curl for HEALTHCHECK probes."""
        content = _read_dockerfile()
        self.assertIn(
            "curl",
            content,
            "Dockerfile must install curl (required by the HEALTHCHECK probe). "
            "Add: RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*",
        )


# ---------------------------------------------------------------------------
# HEALTHCHECK directive
# ---------------------------------------------------------------------------


class TestDockerfileHealthCheck(unittest.TestCase):
    """HEALTHCHECK directive must be present for orchestrator readiness signalling."""

    def test_healthcheck_directive_present(self):
        """HEALTHCHECK must be declared so orchestrators can determine readiness."""
        content = _read_dockerfile()
        self.assertRegex(
            content,
            r"(?m)^HEALTHCHECK\b",
            "Dockerfile must have a HEALTHCHECK directive so container orchestrators "
            "(Docker Compose, Kubernetes) can detect service readiness",
        )

    def test_healthcheck_uses_curl_or_wget(self):
        """HEALTHCHECK CMD should probe the HTTP endpoint via curl or wget."""
        content = _read_dockerfile()
        # Find the HEALTHCHECK line(s)
        hc_match = re.search(
            r"HEALTHCHECK.*",
            content,
            re.DOTALL,
        )
        if not hc_match:
            self.fail("No HEALTHCHECK directive found in Dockerfile")
        hc_text = hc_match.group(0)[:300]  # limit to avoid huge matches
        self.assertTrue(
            "curl" in hc_text or "wget" in hc_text,
            "HEALTHCHECK CMD should probe the service with curl or wget; "
            f"found: {hc_text!r}",
        )


# ---------------------------------------------------------------------------
# Layer-cache optimisation
# ---------------------------------------------------------------------------


class TestDockerfileLayerCaching(unittest.TestCase):
    """requirements.txt must be copied before source code to cache pip layer."""

    def test_requirements_txt_copied_before_source(self):
        """COPY requirements.txt must appear before COPY of application source."""
        content = _read_dockerfile()
        copy_lines = [
            (i, line.strip())
            for i, line in enumerate(content.splitlines())
            if line.strip().upper().startswith("COPY")
        ]
        req_indices = [
            i for i, line in copy_lines
            if "requirements.txt" in line or "requirements" in line.lower()
        ]
        src_indices = [
            i for i, line in copy_lines
            if "requirements" not in line.lower()
        ]
        self.assertTrue(
            req_indices,
            "Dockerfile must COPY requirements.txt explicitly; "
            "this layer is cached until dependencies change, speeding up rebuilds",
        )
        if src_indices:
            first_src = min(src_indices)
            first_req = min(req_indices)
            self.assertLess(
                first_req,
                first_src,
                "COPY requirements.txt must appear BEFORE the COPY of application source "
                "so the pip install layer is cached until dependencies change",
            )


# ---------------------------------------------------------------------------
# Port exposure
# ---------------------------------------------------------------------------


class TestDockerfilePortExposure(unittest.TestCase):
    """Dockerfile must EXPOSE port 8000 (FastAPI default)."""

    def test_port_8000_is_exposed(self):
        """EXPOSE 8000 must be declared so docker-compose and orchestrators know the port."""
        content = _read_dockerfile()
        self.assertRegex(
            content,
            r"(?m)^EXPOSE\s+8000\b",
            "Dockerfile must EXPOSE 8000 (the FastAPI service port)",
        )


if __name__ == "__main__":
    unittest.main()
