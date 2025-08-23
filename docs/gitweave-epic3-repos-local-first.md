# GitWeave — Epic 3: Repositories Core (Local‑First MVP)

**Goal:** Provide Git repository hosting, creation, listing, and clone/push over **HTTP(S)** and **SSH**, fully runnable **locally**. Auth integrates with Epic 1 (sessions/PATs/SSH keys).

---

## Scope (MVP)
- Create/list/delete repositories within the default org/project (project scaffolding optional for MVP).
- Bare repo storage on local filesystem (e.g., `/data/repos/<repo>.git`).
- Git over **HTTP (smart)** via `git-http-backend` behind the API gateway with auth (PAT or basic session).
- Git over **SSH** via `sshd` + `git-shell` forced command wrapper.
- Branch protection (read‑only placeholder rules stored; enforcement added later when PRs land).
- Simple repo‑level permissions: Maintainers (RW), Developers (RW), Guests (R).

### Out of Scope (MVP)
- Pull requests, code review UI.
- Web UI for file browser (readme rendering optional nice‑to‑have).
- LFS (later).

---

## Architecture (Local‑First)
- **repo‑svc**: REST for repo CRUD; owns filesystem paths; shells out to `git init --bare` and basic maintenance.
- **git‑http**: nginx (or tiny Go proxy) that forwards `/git/<repo>.git/*` to `git-http-backend` with `GIT_PROJECT_ROOT=/data/repos` and `PATH_INFO` set; enforces auth via PAT (Bearer) or Basic if we allow username:PAT.
- **ssh‑gitd**: OpenSSH `sshd` with `ForceCommand` to `git-serve` wrapper which runs `git-upload-pack`/`git-receive-pack` **after** calling `auth‑svc` to map SSH key → user and authorize operation.
- **api‑gateway**: Issues auth; proxies to repo‑svc and git‑http; serves UI.
- **db**: Postgres.

---

## Data Model (SQL)
- **repos**(id uuid PK, org_id, name unique within org, description, visibility ENUM('private','internal','public'), default_branch, created_by, created_at, updated_at, archived_at)
- **repo_members**(repo_id, user_id, role ENUM('maintainer','developer','guest'), PK(repo_id,user_id))
- **branch_rules**(repo_id, pattern, require_up_to_date bool, require_signed_commits bool, require_status_checks bool, created_at)

Filesystem layout:
```
/data/repos/
  my-api.git/
  web-frontend.git/
```

---

## REST API (MVP)
Base path: `/api/v1`

- `POST /repos` → { name, visibility } ⇒ creates bare repo at `/data/repos/<name>.git`, sets default branch on first push.
- `GET /repos` → list repos (name, visibility, last activity).
- `GET /repos/{name}` → repo details.
- `DELETE /repos/{name}` → archive/delete (config: soft delete = move to `/data/archived`).

- `GET /repos/{name}/members` / `PUT /repos/{name}/members/{userId}` (role).
- `GET /repos/{name}/branches` (enumerate via `git for-each-ref`)
- `GET /repos/{name}/branches/rules` / `PUT ...` (store only; enforcement later).

HTTP Git endpoints (proxied, not part of REST surface):
- `/git/{name}.git/info/refs?service=git-upload-pack`
- `/git/{name}.git/git-upload-pack`
- `/git/{name}.git/git-receive-pack`

Auth for HTTP Git:
- `Authorization: Bearer <PAT>` or Basic with `username:any` and `password=<PAT>`.
- PAT must have `git:read` for fetch and `git:write` for push.

SSH Git:
- Remote: `git@localhost:<name>.git`
- `sshd` `ForceCommand` runs `git-serve <op> <repo>`, which calls `auth-svc` with the presented key fingerprint to resolve user & check `git:*` scopes/roles. Deny if unauthorized.


---

## Repo Creation Flow
1. User (maintainer) calls `POST /repos {name}`.
2. repo‑svc checks name, creates `/data/repos/<name>.git` with `git init --bare`.
3. Adds default server hooks folder (empty), writes a `gitweave.meta` file with repo UUID.
4. Returns 201.

## Clone/Push (HTTP) Flow
1. Developer creates PAT with `git:read`/`git:write`.
2. `git clone http://localhost:8080/git/my-api.git` with header `Authorization: Bearer <PAT>`.
3. Proxy validates PAT → `git-http-backend` serves pack.
4. Push uses same header; backend updates refs. repo‑svc emits “repo activity” event.

## Clone/Push (SSH) Flow
1. Developer uploads SSH key (Epic 1).
2. `git clone ssh://git@localhost/my-api.git`.
3. `sshd` runs forced command → `git-serve receive-pack` etc.; `git-serve` asks `auth‑svc` for user by key fingerprint; authorizes action.

---

## Minimal UI (Nice‑to‑have for MVP)
- Repos list, create form, visibility toggle.
- Quick copy buttons for clone URLs (HTTP+SSH).
- Member role table (inline edit).

---

## Acceptance Criteria
- Create repo via REST; repo folder exists and is a valid bare repo.
- Clone over HTTP with PAT works; push updates refs.
- Clone over SSH with uploaded key works; push updates refs.
- Unauthorized users/PATs/keys are rejected with correct status (401/403).
- Deleting (archiving) a repo removes it from list and blocks new pushes.

---

## Test Plan
- Unit: repo name validator, path resolver (no traversal), wrapper around git binaries.
- Integration: end‑to‑end clone/push over HTTP and SSH in docker compose; failure cases (bad PAT, revoked key).
- Performance (smoke): push repo with 10k small files; measure time; ensure no crash.


---

## Config (env)
```
REPO_ROOT=/data/repos
REPO_ARCHIVE_ROOT=/data/archived
GIT_HTTP_BACKEND=/usr/libexec/git-core/git-http-backend   # or `which git-http-backend`
SSH_FORCE_COMMAND=/srv/gitweave/bin/git-serve
```

---

## Security Notes
- Validate repo names against whitelist regex `^[a-zA-Z0-9._-]+$` (no slashes).
- Never interpolate user input directly into shell calls; use exec with args.
- Set umask and repo ownership to `git:git` service user.
- For HTTP, strip credentials from logs.
- For SSH, `authorized_keys` entries include `command="...",no-agent-forwarding,no-pty,no-port-forwarding`.

---

## Future (Post‑MVP)
- LFS, repo importers, README rendering.
- Protected branches enforcement + status checks.
- Web file browser & blame.
- Mirror/remote sync (pull/push).

