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
