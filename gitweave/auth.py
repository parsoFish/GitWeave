"""GitHub App authentication for gitweave."""

import json
import os
import subprocess
import time
import urllib.request
from github import Github, Auth

# Module-level token cache — valid for one process lifetime.
# Each `gw overlay apply` subprocess needs only one installation token; without
# caching, get_installation_token() makes a fresh JWT exchange per API call
# (8+ per apply), which trips GitHub's connection-level throttling.
_cached_token: str | None = None
_cached_token_expiry: float = 0.0


class CallerTokenRequiredError(EnvironmentError):
    """Raised when no caller token is available."""


def get_caller_token() -> str:
    """Return caller token from GW_CALLER_TOKEN or 'gh auth token'.

    Raises CallerTokenRequiredError if neither is available.
    Never returns an empty string or None.
    """
    token = os.environ.get("GW_CALLER_TOKEN", "").strip()
    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
        )
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
    except FileNotFoundError:
        pass  # gh not installed

    raise CallerTokenRequiredError(
        "caller-token-required: set GW_CALLER_TOKEN or authenticate with 'gh auth login'"
    )


def resolve_caller_login(token: str, api_url: str = "https://api.github.com") -> str:
    """Resolve the GitHub login for *token* via GET /user.

    Uses urllib.request so tests can mock urllib.request.urlopen.

    Raises CallerTokenRequiredError if the token is rejected (401).
    """
    req = urllib.request.Request(
        f"{api_url}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data["login"]
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise CallerTokenRequiredError(
                "caller-token-required: token rejected by GitHub API (401)"
            ) from exc
        raise

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


def get_installation_auth() -> Auth.AppInstallationAuth:
    """Return the AppInstallationAuth object (has .token property).

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

    with open(key_path, "r") as fh:
        private_key = fh.read()

    app_auth = Auth.AppAuth(
        app_id=int(env["GW_APP_ID"]),
        private_key=private_key,
    )
    return Auth.AppInstallationAuth(
        app_auth=app_auth,
        installation_id=int(env["GW_APP_INSTALLATION_ID"]),
    )


def get_installation_token() -> str:
    """Return the GitHub App installation access token string.

    The token is cached for the process lifetime (with a 5-minute early-expiry
    buffer).  Without caching, each API call made by the live transport handler
    would exchange a fresh JWT for a new installation token, hitting GitHub's
    connection-level throttle on the /installations/{id}/access_tokens endpoint.

    AppInstallationAuth.token requires withRequester() to be called first,
    which happens inside Github(auth=...).  We create a client to prime the
    requester, then read the token back from our local auth reference.
    """
    global _cached_token, _cached_token_expiry

    # Return cached token if still fresh (5-minute buffer before expiry).
    now = time.monotonic()
    if _cached_token is not None and now < _cached_token_expiry:
        return _cached_token

    env = _check_env()

    key_path = env["GW_APP_PRIVATE_KEY_PATH"]
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"Private key file not found: {key_path!r} (GW_APP_PRIVATE_KEY_PATH)"
        )

    with open(key_path, "r") as fh:
        private_key = fh.read()

    app_auth = Auth.AppAuth(
        app_id=int(env["GW_APP_ID"]),
        private_key=private_key,
    )
    install_auth = Auth.AppInstallationAuth(
        app_auth=app_auth,
        installation_id=int(env["GW_APP_INSTALLATION_ID"]),
    )
    # Github.__init__ calls install_auth.withRequester(requester), enabling
    # install_auth.token to exchange the JWT for an installation access token.
    Github(auth=install_auth)
    token = install_auth.token

    # Cache for 55 minutes (tokens are valid for 1 hour; 5-minute buffer).
    _cached_token = token
    _cached_token_expiry = now + 3300

    return token


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

    with open(key_path, "r") as fh:
        private_key = fh.read()

    app_auth = Auth.AppAuth(
        app_id=int(env["GW_APP_ID"]),
        private_key=private_key,
    )
    auth = Auth.AppInstallationAuth(
        app_auth=app_auth,
        installation_id=int(env["GW_APP_INSTALLATION_ID"]),
    )
    return Github(auth=auth)
