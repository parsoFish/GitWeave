# GitWeave Copilot Instructions

This file provides context for GitWeave development when working with GitHub Copilot.

## Overview
GitWeave is an opinionated Git platform (similar to GitHub/GitLab/ADO) with the following key differentiators:
- **Built‑in DORA Metrics**: Native computation of deployment frequency, lead time, MTTR, and change failure rate directly from platform data (no external integrations like LinearB required).
- **Opinionated Build System**: Core platform maintains standardized build, test, and release templates. DevOps teams can centrally update patterns which apply across all repositories, without per‑repo CI/CD authoring.

## Documentation Structure
All epic specifications and supporting docs are stored under the `/docs` folder.  
Use [../docs/docs-README.md](../docs/docs-README.md) as the table of contents for navigation.

Key files:
- `gitweave-epic-map.md` — overview of epics and domain objects
- `gitweave-domain-model.md` — Mermaid diagram of entities and flows
- `gitweave-epicX-*.md` — detailed specs for each epic (MVP scope + out of scope)
- `docker-compose.local.yml` — local-first development setup

## Domain Model (Core Entities)
- **Identity & Access**: Authentication, Users, Teams, Permissions
- **Repositories**: Repositories, BranchingStrategies
- **Work Items**: WorkItemBacklog, links to commits/releases
- **Pipelines**: PipelineRunner, PipelineInterpreter, Build, TestRun, Release, Jobs, Logs
- **Templates**: BuildTemplate, TestTemplate, ReleaseTemplate
- **Artifacts**: ArtifactStore, Package, Artifact
- **Integrations**: ServiceConnections (AWS/GCP/Azure, Docker registry, generic key/value)
- **Metrics**: DoraSnapshot, computed from repo + pipeline + release data

## Local‑First MVP Principles
- **No cloud dependencies**: everything must run in Docker Compose locally with Postgres and mounted volumes.
- **No external identity providers**: only local email/password, PATs, SSH keys for now.
- **No external artifact storage**: artifacts live in `/data/artifacts` volume.
- **No external integrations**: service connections exist but only basic generic/aws/docker creds are supported.

## Key Epics (MVP)
- Authentication & Identity
- Teams & Permissions
- Repositories Core
- Work Item Backlog
- Platform Core (Opinionated Templates ⭐)
- Pipeline Runner & Interpreter
- Build Module
- Test Module
- Release Module
- Artifact Storage & Package Mgmt
- Service Connections
- Built‑in DORA Metrics ⭐

## Implementation Conventions
- **Passwords**: Argon2id hashing, 16‑byte salt, optional pepper from env.
- **PATs**: hashed in DB, only shown once; prefix tokens with `gw_pat_`.
- **SSH keys**: validate key type/length, store in DB, sync to `authorized_keys`.
- **Repo names**: whitelist regex `^[a-zA-Z0-9._-]+$`, no slashes.
- **Artifacts**: checksum with SHA‑256, stored under `/data/artifacts/<repo>/<buildId>/`.
- **Test reports**: JUnit XML (primary), Cobertura/LCOV for coverage summary.
- **Releases**: metadata only in MVP, deployments are records not infra actions.

## Out‑of‑Scope (MVP)
When generating code or APIs, do **not** implement these yet (stub only if needed):
- SSO/OIDC/SAML, SCIM, MFA/WebAuthn
- Nested teams, custom roles, audit trails
- Pull requests / code reviews
- UI boards for work items
- Template inheritance, canary rollout
- Multi‑runner clusters, DAG scheduling
- Remote artifact storage or package registries
- Secrets rotation/advanced providers
- MTTR/CFR metrics, dashboards

## Guiding Principles
- **Centralized patterns**: Developers attach pre‑defined templates rather than writing bespoke pipelines.
- **Scalability**: Design modularly for future scaling, but MVP = single docker-compose cluster.
- **Security**: Enforce local security best practices (hashed tokens, key validation, env secrets).
- **DX Focus**: Fast feedback cycles, simple defaults, rich templates.

## Codename
Working codename: **GitWeave**

---

When writing code or documentation with Copilot, ensure outputs:
1. Reference the `/docs` folder and epic specs when defining services, schemas, or APIs.
2. Respect the **MVP scope vs out‑of‑scope** boundaries listed above.
3. Use the domain model and epic map as the source of truth for entities and relationships.
4. Emphasize built‑in DORA metrics and opinionated build system whenever relevant.

## Development Process Policy (TDD)
- Practice test‑driven development for all epics. Start by updating/adding tests that capture the MVP acceptance criteria from the epic docs.
- For Epics 1 and 3, use the Node/Vitest test harness under `tests/` as the canonical contract tests. Keep tests small, deterministic, and idempotent.
- Work iteratively: adjust tests or implementation as needed to reflect intended behavior, but do not change tests and implementation in the same change. Prefer a small commit that updates tests (with rationale) followed by a small commit that updates code to satisfy them.
- Maintain mapping from tests to epic acceptance criteria in test descriptions. Prefer one spec per API surface or flow.
- E2E tests may be skipped by default and gated by env flags until the local stack (docker compose) is available.

### Test Contract Guardrail
- Treat tests as the contract. When behavior needs to change, update tests first with a short justification that maps to the epic spec, then implement the code in a separate change.
- Never land changes that modify tests and implementation together; keep them separate to avoid masking regressions.
- Keep tests deterministic and idempotent; short‑circuit via env flags for networked/E2E suites.

## Running Tests (Local‑First)
- Unit/Integration API tests (Epics 1 & 3): set `RUN_API_TESTS=1` and point `API_BASE_URL` to the running API (default `http://localhost:8080/api/v1`).
- E2E Git tests: set `RUN_E2E_HTTP=1` and/or `RUN_E2E_SSH=1`. Provide `GITWEAVE_PAT` for HTTP. Ensure docker compose stack is up.

Examples:
- `npm run test` → static spec checks (skips networked tests by default)
- `npm run test:api` → runs API suites with `RUN_API_TESTS=1`
- `npm run test:e2e` → runs E2E suites (HTTP+SSH) if services are up

## Workspace Layout & Paths
Keep these paths in mind when running commands to avoid context issues:
- Root (this repo): project orchestrator for tests and scripts
	- `app/` — Express API (TypeScript). Build with `npm --prefix app run build` and run with `node app/dist/index.js`.
	- `ui/` — Vite + React client (TypeScript). Dev with `npm --prefix ui run dev` (http://localhost:5173).
	- `tests/` — Vitest suites (TypeScript) for API/E2E.
	- `docs/` — Design and epic specs.
	- `.github/` — Copilot guidance and CI config.

Path tips:
- From root, prefer `npm --prefix app <cmd>` instead of `cd app` when scripting.
- Default API base URL for tests and examples: `http://localhost:8080/api/v1`.
- Windows PowerShell: join commands with `;` where needed in ad‑hoc use. In npm scripts, use `&&` for sequencing.

## Coding Best Practices (concise)
TypeScript (tests and app):
- Enable strict typing; avoid `any`. Use narrow DTO shapes for request/response.
- Prefer small, pure helpers; keep side effects at the edges (routes, IO).
- Validate inputs; return JSON `{ error: { code, message } }` with appropriate HTTP status.

Node/Express API:
- Parse JSON and cookies early; never trust client input.
- Authenticate via cookie session or Bearer PAT; return 401 on missing/invalid auth.
- Keep in‑memory stores isolated for MVP; future: replace with Postgres per epics.

Testing (Vitest):
- Keep tests deterministic and idempotent; avoid global state leakage.
- Short‑circuit tests via env flags; do not modify existing tests during feature work.

Performance & DX:
- Use minimal dependencies; pin major versions. Keep builds fast.
- Prefer iterative patches over large refactors. Keep this file short; link out to `/docs` for details.

## Context Discipline
- When working on a specific component, load all relevant files into context so changes remain consistent:
	- API routes/handlers: `app/src/**`, plus related tests under `tests/**` and any shared utils.
	- UI feature: affected files in `ui/src/**`, its API calls, and the corresponding backend endpoints in `app/src/**`.
	- Scripts/tooling: `scripts/**`, related `package.json` scripts, and any files they orchestrate.
- Before editing, scan for usages and contracts (tests, types, DTOs). After editing >3 files, pause and run build/tests.
