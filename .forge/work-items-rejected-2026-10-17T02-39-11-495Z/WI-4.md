---
work_item_id: WI-4
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on: []
domain: transport
acceptance_criteria:
  - given: "code that uses RecordingTransport to intercept HTTP calls"
    when: "the overlay apply path runs (create branch)"
    then: "the recording transport's request log contains zero entries matching POST /repos/*/pulls"
  - given: "a deliberate code mutant that calls POST /repos/{owner}/{repo}/pulls inside the overlay apply path"
    when: "the recording transport test runs"
    then: "the assertion fails — proving the recording transport catches the violation"
  - given: "both the self-serve code path and the overlay apply code path"
    when: "they are invoked through the recording transport"
    then: "both paths' HTTP calls are captured in the same request log"
  - given: "GW_CONTROL_REPO is referenced in the codebase"
    when: "grep runs over gitweave/"
    then: "no occurrences found; _assert_no_control_repo_pr and GW_CONTROL_REPO are removed"
files_in_scope:
  - gitweave/transport.py
  - tests/test_recording_transport.py
creates:
  - gitweave/transport.py
  - tests/test_recording_transport.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_recording_transport.py::TestRecordingTransport::test_zero_post_repos_pulls_overlay_path"
  - "-p"
  - "no:cacheprovider"
---

# WI-4: Recording transport + no-PR invariant (I3b residual #7)

Target: `gitweave/transport.py` (new), `tests/test_recording_transport.py` (new).

This WI removes the `_assert_no_control_repo_pr` / `GW_CONTROL_REPO` pattern (I3b residual #7) and replaces it with a transport-level recording approach.

## Implementation: gitweave/transport.py

```python
"""HTTP transport abstraction for GitWeave.

RecordingTransport captures every outbound HTTP request so tests can assert
on the full call log (e.g. zero POST /repos/*/pulls).
"""

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RecordedRequest:
    method: str       # "GET", "POST", etc.
    url: str          # full URL


@dataclass
class RecordingTransport:
    """A transport that delegates to a real or fake handler and records all calls.

    Usage in tests:
        transport = RecordingTransport(handler=fake_github_handler)
        # ... run code under test using this transport ...
        transport.assert_no_pr_opens()
    """
    handler: Callable  # callable(method, url, **kwargs) -> response
    requests: list[RecordedRequest] = field(default_factory=list)

    def request(self, method: str, url: str, **kwargs):
        self.requests.append(RecordedRequest(method=method.upper(), url=url))
        return self.handler(method, url, **kwargs)

    def assert_no_pr_opens(self):
        """Assert zero POST /repos/*/pulls requests were made."""
        pr_opens = [
            r for r in self.requests
            if r.method == "POST" and re.search(r"/repos/[^/]+/[^/]+/pulls$", r.url)
        ]
        if pr_opens:
            urls = [r.url for r in pr_opens]
            raise AssertionError(
                f"Expected zero POST /repos/*/pulls calls but found {len(pr_opens)}: {urls}"
            )

    def filter(self, method: str, pattern: str) -> list[RecordedRequest]:
        """Return requests matching method and URL glob pattern."""
        return [
            r for r in self.requests
            if r.method == method.upper() and fnmatch.fnmatch(r.url, pattern)
        ]
```

## Integration guidance for other WIs

WIs that implement overlay apply (WI-6) and self-serve overlay request (WI-9) MUST use `RecordingTransport` in their tests and call `transport.assert_no_pr_opens()` at the end of each test that exercises the write path.

Pattern:
```python
def fake_handler(method, url, **kwargs):
    # return pre-baked response objects
    ...

def test_overlay_apply_no_pr(self):
    transport = RecordingTransport(handler=fake_handler)
    # call overlay apply code wired through transport
    transport.assert_no_pr_opens()
```

## Remove GW_CONTROL_REPO and _assert_no_control_repo_pr

Search for and remove:
- Any `_assert_no_control_repo_pr` function definition and all call sites
- Any `GW_CONTROL_REPO` environment variable references
- Any test fixture that sets `GW_CONTROL_REPO`

These existed as a proxy for the no-PR invariant. They are replaced by the recording transport pattern.

## Test file: tests/test_recording_transport.py

Class `TestRecordingTransport`:

- `test_zero_post_repos_pulls_overlay_path` — runs a fake overlay apply (simulating a create branch call via a stub handler), asserts `transport.assert_no_pr_opens()` passes
- `test_mutant_pr_open_detected` — runs a fake handler that opens a PR (`POST /repos/org/repo/pulls`), asserts `transport.assert_no_pr_opens()` raises `AssertionError`
- `test_records_all_http_calls` — verifies `transport.requests` grows with each call
- `test_filter_by_method_and_pattern` — verifies `transport.filter()` returns correct subset
- `test_self_serve_path_intercepted` — simulates a self-serve call through the same transport, asserts the call is recorded

Tests must NOT inherit any GW_* autouse fixture.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
