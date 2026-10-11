"""GitHub App authentication for gitweave."""

import os
from github import Github, Auth

REQUIRED_ENV = [
    "GW_APP_ID",
    "GW_APP_PRIVATE_KEY_PATH",
    "GW_APP_INSTALLATION_ID",
    "GW_ORG",
]


def _check_env() -> dict:
    """Return env dict; raise EnvironmentError naming first missing var."""
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )
    return {v: os.environ[v] for v in REQUIRED_ENV}


def get_github_client() -> Github:
    """Return an installation-authenticated Github client.

    Raises:
        EnvironmentError: if any required env var is unset.
        FileNotFoundError: if GW_APP_PRIVATE_KEY_PATH does not exist.
    """
    env = _check_env()

    key_path = env["GW_APP_PRIVATE_KEY_PATH"]
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"Private key file not found: {key_path!r} (GW_APP_PRIVATE_KEY_PATH)"
        )

    with open(key_path, "rb") as fh:
        private_key = fh.read()

    auth = Auth.AppInstallationAuth(
        app_id=int(env["GW_APP_ID"]),
        private_key=private_key,
        installation_id=int(env["GW_APP_INSTALLATION_ID"]),
    )
    return Github(auth=auth)
