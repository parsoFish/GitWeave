# GitWeave

An opinionated, local‑first Git platform with built‑in DORA metrics and a centralized, template‑driven CI/CD model. This repo currently contains:
- Express API (TypeScript) for Auth and Repos MVP
- Vite + React UI for basic flows
- Vitest contract tests for Epic 1 (Auth) and Epic 3 (Repos)
- Design docs and epic specs under `docs/`

See `docs/docs-README.md` for the full epic map and domain model.

## Highlights
- Local‑first MVP: no cloud dependencies, runs on your machine
- Built‑in DORA metrics (planned per epics); opinionated templates (planned)
- Auth: email/password sessions + PATs; SSH key CRUD (MVP)
- Repos: metadata CRUD and branch rules (MVP, no Git protocol yet)

## Monorepo layout
- `app/` — API server (Express, TypeScript)
- `ui/` — Web UI (Vite + React)
- `tests/` — Vitest suites (API contracts, E2E stubs)
- `scripts/` — Dev and test orchestration
- `docs/` — Specs and diagrams

## Prereqs
- Node.js 20+ (22 recommended)
- Windows PowerShell (or any shell) for the examples below

## Install
```powershell
# Root dev tools and tests
npm install

# API service deps
npm --prefix app install

# UI deps
npm --prefix ui install
```

## Run (dev)
```powershell
# Start API (http://localhost:8080) + UI (http://localhost:5173)
npm run dev
```
- UI proxies `/api` → `http://localhost:8080`
- API readiness: `GET http://localhost:8080/healthz` → `{ status: "ok" }`

## Try it
1) Sign up (first user becomes owner internally; current tests default role display is `developer` on signup response)
2) Log in, create a PAT, call protected endpoints using `Authorization: Bearer <token>`

Key endpoints (prefix `/api/v1`):
- Auth: `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`
- PATs: `POST /auth/pat`, `GET /auth/pat`, `DELETE /auth/pat/:id`
- SSH: `POST/GET/DELETE /auth/ssh-keys`
- Orgs: `GET /orgs/current`
- Repos: `POST/GET /repos`, `GET /repos/:name`, `PUT/GET /repos/:name/branches/rules`, `DELETE /repos/:name`

## Tests
- API contracts (builds, boots API, waits for readiness, runs tests):
```powershell
node .\scripts\test-api-with-app.mjs
```
- Run against an already‑running API:
```powershell
$env:RUN_API_TESTS=1; $env:API_BASE_URL="http://localhost:8080/api/v1"; npm run test:api
```

## Troubleshooting
- Port 8080 in use: stop the existing API, or set `PORT=8081` and update the UI proxy if needed.
- Session cookie in dev: the UI uses a Vite proxy so cookies are same‑origin (`/api`) and sent by default.

## License
This project is licensed under the PolyForm Noncommercial 1.0.0 license. Non‑commercial use is permitted; commercial use requires a separate license. See `LICENSE.md`.

---
Made with GitWeave’s local‑first principles. See the epics under `docs/` to track progress and scope.
