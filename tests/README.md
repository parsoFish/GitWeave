# GitWeave Tests (Epics 1 & 3 MVP)

This folder contains the initial contract and E2E tests for:
- Epic 1: Authentication & Identity (Local‑First MVP)
- Epic 3: Repositories Core (Local‑First MVP)

Tests are written with Vitest and default to skipping networked checks unless explicitly enabled.

## Structure
- `auth/` → Auth API specs (signup/login/session, PATs, SSH keys).
- `repos/` → Repo API specs (create/list/get/delete, branch rules).
- `e2e/` → Git over HTTP/SSH E2E flows (clone + push). Skipped by default.
- `utils/` → Helpers for env and HTTP client with cookie jar.

## Prereqs
- Node.js 18+ (Node 20 recommended)
- Optional: Docker (to run the local stack), Git CLI available in PATH

Install dev deps:

```powershell
npm i
```

## Running
- Static run (no network):
```powershell
npm test
```

- API contract tests against a running API (defaults to http://localhost:8080/api/v1):
```powershell
$env:RUN_API_TESTS=1; npm run test:api
# or override base URL
$env:RUN_API_TESTS=1; $env:API_BASE_URL='http://localhost:8080/api/v1'; npm test
```

- E2E Git over HTTP (requires PAT with git:read,git:write):
```powershell
$env:RUN_E2E_HTTP=1; $env:GITWEAVE_PAT='gw_pat_xxx'; npm run test:e2e
```

- E2E Git over SSH (requires authorized key and sshd at localhost:2222):
```powershell
$env:RUN_E2E_SSH=1; npm run test:e2e
```

## Notes
- Tests are idempotent where possible and account for existing resources with HTTP 409 expectations.
- SSH key test uses a placeholder public key by default. Set `TEST_SSH_PUBKEY` to a real key for a full run.
- Keep test names aligned with the acceptance criteria in the epic docs.
