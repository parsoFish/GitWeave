---
work_item_id: WI-2
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on: []
acceptance_criteria:
  - given: "GW_CALLER_TOKEN is set to a valid token string"
    when: "get_caller_token() is called"
    then: "returns that token value without invoking gh"
  - given: "GW_CALLER_TOKEN is not set and 'gh auth token' returns a token on stdout"
    when: "get_caller_token() is called"
    then: "returns the token from gh auth token"
  - given: "GW_CALLER_TOKEN is not set and 'gh auth token' fails (non-zero exit or empty output)"
    when: "get_caller_token() is called"
    then: "raises CallerTokenRequiredError with a message including 'caller-token-required'; never returns None or an empty string"
  - given: "a valid caller token that the GitHub API /user endpoint can resolve"
    when: "resolve_caller_login(token) is called (using a mock HTTP client)"
    then: "returns the login string from the API response"
  - given: "a caller token that the GitHub API rejects (401)"
    when: "resolve_caller_login(token) is called"
    then: "raises CallerTokenRequiredError"
files_in_scope:
  - gitweave/auth.py
  - tests/test_caller_auth.py
creates:
  - tests/test_caller_auth.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_caller_auth.py::TestCallerAuth::test_missing_token_raises"
  - "-p"
  - "no:cacheprovider"
domain: "auth"
---

# WI-2: Two-identity auth — caller token resolution

Target: extend `gitweave/auth.py` with caller-identity primitives. The GitHub App authentication (`get_github_client`) is unchanged; this WI adds the caller-token layer that self-serve commands use.

## New exception

```python
class CallerTokenRequiredError(EnvironmentError):
    """Raised when no caller token is available."""
```

## New functions in auth.py

```python
def get_caller_token() -> str:
    """Return caller token from GW_CALLER_TOKEN or 'gh auth token'.

    Raises CallerTokenRequiredError if neither is available.
    Never returns an empty string or None.
    """

def resolve_caller_login(token: str, api_url: str = "https://api.github.com") -> str:
    """Resolve the GitHub login for *token* via GET /user.

    Uses urllib.request (no extra dep) so tests can mock at the socket level
    or by patching urllib.request.urlopen.

    Raises CallerTokenRequiredError if the token is rejected (401).
    """
```

## Security note

Never log or print the token value. Tests use fake token strings; no real token appears in committed code.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
