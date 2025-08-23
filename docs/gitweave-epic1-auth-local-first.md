# GitWeave — Epic 1: Authentication & Identity (Local‑First MVP)

**Goal:** Provide a minimal, secure authentication/identity layer that runs entirely **locally** for development. Cloud SSO can be added later without refactoring the core domain.

---

## Scope (MVP)
- Local email/password accounts with strong hashing (Argon2id).
- Session cookies (HTTP‑only, SameSite=Lax) for the web UI.
- Personal Access Tokens (PATs) for CLI/HTTP Git operations.
- SSH public key management (for Git over SSH, used by Epic 3).
- Basic organizations scaffold: single default org created at bootstrap (future multi‑org ready).
- Admin bootstrap (first user becomes Org Owner).

### Out of Scope (MVP)
- External SSO (OIDC/SAML) — placeholder config stubs only.
- SCIM provisioning.
- MFA/WebAuthn (planned next).
- Fine‑grained RBAC UI (we’ll ship Owner/Maintainer/Developer roles with minimal rules).

---

## Personas
- **Developer**: signs up, generates PAT, uploads SSH key.
- **Org Admin**: initial bootstrap, manages users and roles.

---

## Architecture (Local‑First)
- **api‑gateway** (HTTP): serves UI + REST/JSON APIs; issues sessions; validates PATs.
- **auth‑svc**: user store, Argon2 hashing, session issuing/validation, PAT/SSH key CRUD.
- **db**: Postgres (or SQLite for pure single‑file local dev; we’ll start Postgres for parity).
- **secrets**: `.env` for local; mounts into services.
- **ssh‑gitd**: OpenSSH `sshd` configured to use `git-shell`/forced command; reads `authorized_keys` rendered from `auth‑svc` (see Epic 3).

> For simple local bring‑up we can merge `api‑gateway` + `auth‑svc` in one container (“app”). Separate binaries remain in the repo to ease later split.

---

## Data Model (SQL)
### tables
- **users**(id uuid PK, email unique, name, password_hash, is_admin bool, created_at, updated_at, disabled_at)
- **orgs**(id uuid PK, name unique, created_at)
- **org_members**(org_id, user_id, role ENUM('owner','maintainer','developer','reporter','guest'), PK(org_id,user_id))
- **sessions**(id uuid PK, user_id, created_at, expires_at, ip, ua, revoked_at)
- **personal_access_tokens**(id uuid PK, user_id, name, token_prefix, token_hash, scopes jsonb, created_at, last_used_at, revoked_at)
- **ssh_keys**(id uuid PK, user_id, name, public_key, created_at, revoked_at)

Indexes on email, token_prefix, user_id.

---

## Security Notes
- Passwords: **Argon2id** (tuned for dev hardware), 16‑byte random salt, pepper via env `AUTH_PASSWORD_PEPPER` (optional).
- PATs: store **hash only** (`token_hash`), display token once on creation, prefix e.g. `gw_pat_...` for UX; scopes (["git:read","git:write","api:read"]).
- Sessions: signed cookies (JWT or random opaque id); store server‑side for revocation.
- CSRF: double‑submit token for form POSTs.
- SSH keys: validate key type (rsa‑sha2‑512/ed25519), size, and uniqueness per user.
- Rate limiting: login + PAT create endpoints (simple leaky bucket in memory for local).

---

## REST API (MVP)
Base path: `/api/v1`

### Auth
- `POST /auth/signup` → { email, name, password } ⇒ 201; first user becomes org owner, creates default org.
- `POST /auth/login` → { email, password } ⇒ Set-Cookie session; 200.
- `POST /auth/logout` → clears session.
- `GET /auth/session` → returns current user summary.
- `POST /auth/pat` → { name, scopes[] } ⇒ returns plaintext token once.
- `GET /auth/pat` → list tokens (prefix + created/lastUsed).
- `DELETE /auth/pat/{id}`
- `POST /auth/ssh-keys` → { name, publicKey } ⇒ validate & store.
- `GET /auth/ssh-keys`
- `DELETE /auth/ssh-keys/{id}`

### Orgs
- `GET /orgs/current` → default org info.
- `GET /orgs/current/members` → membership list.
- `POST /orgs/current/members` (admin) → invite by email (local: creates dormant user until signup).
- `PATCH /orgs/current/members/{userId}` → change role.

> All endpoints return standard error envelope: `{error:{code,message,details?}}`

---

## Roles & Minimal RBAC (MVP)
- **owner**: all org operations.
- **maintainer**: manage repos within org.
- **developer**: push/pull to repos they have access to.
- **reporter/guest**: read‑only (future).

> Epic 3 will check org_members for repo actions; PAT/SSH auth maps to user → role checks.

---

## UX Flows
### Signup/Login
1. User opens UI → signup (email/password/name).
2. System creates default org if first user, assigns `owner`.
3. User logs in; sees “Generate PAT” + “Add SSH Key” prompts.

### Generate PAT
1. POST `/auth/pat` with scopes.
2. Return token once; user copies to `~/.git-credentials` or use as HTTP header `Authorization: Bearer <token>`.

### Add SSH Key
1. POST `/auth/ssh-keys` with `ssh-ed25519 AAAA...`.
2. Key appears in list; `ssh-gitd` will rebuild `authorized_keys` (Epic 3 integration).

---

## Acceptance Criteria
- Can create first account locally; cookie session works across UI/API.
- PAT can authenticate to protected endpoints requiring `api:*` scopes.
- SSH key added appears in `authorized_keys` (via sync job) and permits `git clone ssh://` (Epic 3).
- Disabling a user revokes all sessions and PATs immediately.

---

## Test Plan (MVP)
- Unit: hashing, token prefixing, SSH key parser, validators.
- Integration: signup/login/logout, PAT lifecycle, SSH key lifecycle.
- E2E (docker compose): first user bootstrap; PAT clone against repo (Epic 3).

---

## Config (env)
```
AUTH_SESSION_SECRET=dev_super_secret
AUTH_PASSWORD_PEPPER=optional_pepper
AUTH_COOKIE_DOMAIN=localhost
AUTH_COOKIE_SECURE=false
DB_URL=postgres://gitweave:gitweave@db/gitweave
```

---

## Future (Post‑MVP)
- MFA (TOTP/WebAuthn), device approvals.
- OIDC/SAML providers (Google, Azure AD, Okta).
- SCIM user provisioning.
- Account lockout and audit trail surfacing in UI.
