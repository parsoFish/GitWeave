"""Overlay apply engine — Git Trees API, three state branches.

Applies a single Copier module to a repository atomically:
  Branch 1 (create): no applied state → render, blob, tree, commit, ref
  Branch 2 (unchanged): applied state matches declared triple → skip
  Branch 3 (update): applied state differs → re-render, same API sequence

Never calls POST /repos/*/pulls.
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from gitweave.auth import get_installation_token
from gitweave.module_render import render_module  # noqa: E402

BASE_URL = "https://api.github.com"


class EmptyRepositoryError(Exception):
    """Raised when a GitHub repository has no commits yet (HTTP 409)."""


class RepositoryNotFoundError(Exception):
    """Raised when the target repository does not exist (transport returned None on ref lookup)."""

    def __init__(self, repo_full_name: str) -> None:
        self.repo = repo_full_name
        super().__init__(f"Repository {repo_full_name!r} not found (transport returned None)")


class BranchProtectedError(Exception):
    """Raised when branch protection prevents a ref update (HTTP 422)."""

    def __init__(self, repo: str, branch: str, protection: str) -> None:
        self.repo = repo
        self.branch = branch
        self.protection = protection
        super().__init__(
            f"{repo} branch '{branch}' is protected: {protection}"
        )


@dataclass
class ModuleSpec:
    name: str
    version: str
    inputs: dict[str, Any]


@dataclass
class OverlayApplyResult:
    repo: str
    action: str   # "created" | "updated" | "unchanged"
    message: str


def _module_answers_path(module_name: str) -> str:
    """Return the per-module answers file path inside the repo tree."""
    return f".gitweave/{module_name}.copier-answers.yml"


def _read_applied_state(repo_full_name: str, transport, module_name: str) -> dict | None:
    """GET /repos/{owner}/{repo}/contents/.gitweave/<module>.copier-answers.yml.

    Returns parsed YAML dict or None if file not found.
    """
    resp = transport.request(
        "GET",
        f"{BASE_URL}/repos/{repo_full_name}/contents/{_module_answers_path(module_name)}",
    )
    if resp is None:
        return None
    content_b64 = resp.get("content", "")
    # GitHub API sometimes includes newlines in base64 content
    content_b64 = content_b64.replace("\n", "")
    content = base64.b64decode(content_b64).decode("utf-8")
    return yaml.safe_load(content)


def _is_unchanged(declared: ModuleSpec, applied: dict) -> bool:
    """True iff the (name, version, inputs) triple already matches."""
    return (
        applied.get("_module_name") == declared.name
        and applied.get("_module_version") == declared.version
        and applied.get("_answers", {}) == declared.inputs
    )


def apply_module_to_repo(
    repo_full_name: str,
    module_spec: ModuleSpec,
    transport,
    default_branch: str = "main",
) -> OverlayApplyResult:
    """Apply a single module to a repo via Git Trees API.

    Args:
        repo_full_name: "owner/repo" string.
        module_spec: declared module (name, version, inputs).
        transport: RecordingTransport (or compatible) instance.
        default_branch: branch to commit to (default "main").

    Returns:
        OverlayApplyResult with action "created" | "updated" | "unchanged".
    """
    applied_state = _read_applied_state(repo_full_name, transport, module_spec.name)

    # Branch 2: no change needed
    if applied_state is not None and _is_unchanged(module_spec, applied_state):
        return OverlayApplyResult(
            repo=repo_full_name,
            action="unchanged",
            message="already up to date",
        )

    # Branch 1 (create) or 3 (update): render then commit via Trees API
    with tempfile.TemporaryDirectory() as tmp_dir:
        render_module(module_spec.name, tmp_dir, data=module_spec.inputs)

        # Write per-module answers file into rendered tree
        answers = {
            "_module_name": module_spec.name,
            "_module_version": module_spec.version,
            "_answers": module_spec.inputs,
        }
        answers_dir = Path(tmp_dir) / ".gitweave"
        answers_dir.mkdir(parents=True, exist_ok=True)
        (answers_dir / f"{module_spec.name}.copier-answers.yml").write_text(
            yaml.dump(answers, default_flow_style=False),
            encoding="utf-8",
        )

        # 1. Get current ref → parent commit SHA (409 = empty repo, no commits yet)
        is_empty_repo = False
        current_sha: str | None = None
        parent_tree_sha: str | None = None
        try:
            ref_resp = transport.request(
                "GET",
                f"{BASE_URL}/repos/{repo_full_name}/git/refs/heads/{default_branch}",
            )
            # AC17: transport returns None on 404 (repo absent) — raise a named
            # error so callers get RepositoryNotFoundError, not TypeError.
            if ref_resp is None:
                raise RepositoryNotFoundError(repo_full_name)
            current_sha = ref_resp["object"]["sha"]

            # 2. Get parent tree SHA
            commit_info = transport.request(
                "GET",
                f"{BASE_URL}/repos/{repo_full_name}/git/commits/{current_sha}",
            )
            parent_tree_sha = commit_info["tree"]["sha"]
        except RepositoryNotFoundError:
            raise  # propagate — not an empty-repo condition
        except Exception as exc:
            # PyGithub exceptions expose .status; requests HTTPError exposes
            # .response.status_code — check both so empty-repo 409s are caught
            # regardless of which transport raises.
            status = getattr(exc, "status", None)
            if status is None:
                _resp = getattr(exc, "response", None)
                status = getattr(_resp, "status_code", None)
            msg = str(exc)
            if status == 409:
                is_empty_repo = True
            else:
                raise

        # 3a. Empty repos: Git Database API (/git/blobs, /git/trees, etc.) returns
        # 409 for repos with no git objects at all.  Use the higher-level Contents
        # API (PUT /repos/{owner}/{repo}/contents/{path}) instead — it works on
        # truly uninitialized repos and creates the initial commit automatically.
        if is_empty_repo:
            # AC16: write the answers file LAST so a failure part-way never
            # records the module as applied.  Partition files into non-answers
            # first, answers-file last.
            answers_rel = _module_answers_path(module_spec.name)
            all_files = sorted(Path(tmp_dir).rglob("*"))
            non_answers = [p for p in all_files if p.is_file() and str(p.relative_to(tmp_dir)) != answers_rel]
            answers_files = [p for p in all_files if p.is_file() and str(p.relative_to(tmp_dir)) == answers_rel]
            for path in non_answers + answers_files:
                raw = path.read_bytes()
                content_b64 = base64.b64encode(raw).decode("ascii")
                rel = str(path.relative_to(tmp_dir))
                transport.request(
                    "PUT",
                    f"{BASE_URL}/repos/{repo_full_name}/contents/{rel}",
                    json={
                        "message": (
                            f"chore: apply module"
                            f" {module_spec.name}@{module_spec.version}"
                        ),
                        "content": content_b64,
                        "branch": default_branch,
                    },
                )
            return OverlayApplyResult(
                repo=repo_full_name,
                action="created",
                message=f"applied {module_spec.name}@{module_spec.version}",
            )

        # 3b. Non-empty repo: create blobs for every rendered file
        tree_entries: list[dict] = []
        for path in sorted(Path(tmp_dir).rglob("*")):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            content_b64 = base64.b64encode(raw).decode("ascii")
            blob_resp = transport.request(
                "POST",
                f"{BASE_URL}/repos/{repo_full_name}/git/blobs",
                json={"content": content_b64, "encoding": "base64"},
            )
            rel = str(path.relative_to(tmp_dir))
            tree_entries.append({
                "path": rel,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp["sha"],
            })

        # 4. Create tree (omit base_tree for empty repos — no prior tree exists)
        tree_payload: dict = {"tree": tree_entries}
        if parent_tree_sha is not None:
            tree_payload["base_tree"] = parent_tree_sha
        new_tree = transport.request(
            "POST",
            f"{BASE_URL}/repos/{repo_full_name}/git/trees",
            json=tree_payload,
        )

        # 5. Create commit
        action = "updated" if applied_state else "created"
        commit_payload: dict = {
            "message": f"chore: apply module {module_spec.name}@{module_spec.version}",
            "tree": new_tree["sha"],
            "parents": [current_sha],
        }
        new_commit = transport.request(
            "POST",
            f"{BASE_URL}/repos/{repo_full_name}/git/commits",
            json=commit_payload,
        )

        # 6. Update ref
        try:
            transport.request(
                "PATCH",
                f"{BASE_URL}/repos/{repo_full_name}/git/refs/heads/{default_branch}",
                json={"sha": new_commit["sha"]},
            )
        except Exception as exc:
            status = getattr(exc, "status", None)
            if status is None:
                _resp = getattr(exc, "response", None)
                status = getattr(_resp, "status_code", None)
            msg = str(exc)
            if status == 422:
                raise BranchProtectedError(
                    repo=repo_full_name,
                    branch=default_branch,
                    protection=msg,
                ) from exc
            raise

    return OverlayApplyResult(
        repo=repo_full_name,
        action=action,
        message=f"applied {module_spec.name}@{module_spec.version}",
    )


def get_overlay_status(gh_repo) -> list[dict]:
    """Read applied overlay state from .gitweave/*.copier-answers.yml via PyGitHub.

    Args:
        gh_repo: PyGitHub Repository object.

    Returns:
        List of dicts, one per applied module:
        [{"name": ..., "version": ..., "inputs": {...}}]
        Empty list if .gitweave/ directory is absent or empty.
    """
    try:
        contents = gh_repo.get_contents(".gitweave")
    except Exception as exc:
        status = getattr(exc, "status", None)
        if status == 404:
            return []
        raise

    # get_contents returns a list for directories, a ContentFile for a single file
    if not isinstance(contents, list):
        contents = [contents]

    result = []
    for item in contents:
        if not item.path.endswith(".copier-answers.yml"):
            continue
        decoded = item.decoded_content.decode("utf-8")
        applied = yaml.safe_load(decoded)
        if not applied:
            continue
        result.append({
            "name": applied.get("_module_name"),
            "version": applied.get("_module_version"),
            "inputs": applied.get("_answers", {}),
        })
    return result


def apply_overlays_for_repo(
    repo_name: str,
    gh_org,
    transport=None,
) -> list[OverlayApplyResult]:
    """Apply all declared module overlays for a repository.

    Args:
        repo_name: short repository name (not owner/repo).
        gh_org: PyGitHub Organisation object (provides org login).
        transport: optional RecordingTransport; callers may inject for testing.

    Returns:
        List of OverlayApplyResult, one per declared module.
    """
    from gitweave.config import load_repo_config  # type: ignore[import]

    org_login = gh_org.login
    repo_full_name = f"{org_login}/{repo_name}"

    if transport is None:
        from gitweave.transport import RecordingTransport

        import requests as _req

        def _live_handler(method, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {get_installation_token()}"
            resp = _req.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 404:
                return None  # file/resource not found is valid (e.g. .copier-answers.yml absent)
            resp.raise_for_status()
            return resp.json()

        transport = RecordingTransport(handler=_live_handler)

    repo_config = load_repo_config(repo_name)
    modules = repo_config.get("spec", {}).get("modules", [])

    results: list[OverlayApplyResult] = []
    for mod in modules:
        spec = ModuleSpec(
            name=mod["name"],
            version=mod.get("version", ""),  # version is optional in config; default empty
            inputs=mod.get("inputs", {}),
        )
        try:
            result = apply_module_to_repo(repo_full_name, spec, transport)
        except RepositoryNotFoundError as exc:
            result = OverlayApplyResult(
                repo=repo_full_name,
                action="error",
                message=str(exc),
            )
        results.append(result)

    return results
