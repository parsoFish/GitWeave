"""Offline module rendering via Copier."""

from __future__ import annotations

from pathlib import Path


class CopierVersionError(RuntimeError):
    """Installed Copier is older than module's min_copier_version."""


def _installed_copier_version() -> str:
    """Return installed Copier version string."""
    import copier
    return copier.__version__


def _check_version(module_path: Path) -> None:
    """Raise CopierVersionError if installed Copier < min_copier_version."""
    import yaml
    from packaging.version import Version

    copier_yaml = module_path / "copier.yaml"
    data = yaml.safe_load(copier_yaml.read_text())
    min_ver = data.get("_metadata", {}).get("min_copier_version")
    if min_ver is None:
        return
    installed = _installed_copier_version()
    if Version(installed) < Version(min_ver):
        raise CopierVersionError(
            f"Module requires copier>={min_ver}; installed={installed}"
        )


def render_module(name: str, dest: str, data: dict | None = None) -> None:
    """Render module <name> to <dest> offline.

    Args:
        name: snake_case module name (matches modules/<name>/ directory)
        dest: destination directory path (created if absent)
        data: optional dict of answers overriding copier defaults
    """
    modules_root = Path(__file__).parent.parent / "modules"
    module_path = modules_root / name
    if not module_path.is_dir():
        raise FileNotFoundError(f"Module not found: modules/{name}/")

    _check_version(module_path)

    import copier

    copier.run_copy(
        src_path=str(module_path),
        dst_path=dest,
        data=data or {},
        defaults=True,
        overwrite=True,
        vcs_ref=None,
    )
