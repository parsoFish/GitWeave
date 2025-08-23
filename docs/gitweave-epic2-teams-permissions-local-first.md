# GitWeave — Epic 2: Teams & Permissions (Local‑First MVP)

**Goal:** Provide a minimal RBAC model to control access to repositories and future resources, with support for teams and roles. Local‑first design: runs in Docker compose, no external IAM dependencies.

---

## Scope (MVP)
- Team creation and user membership (manual assignment only).
- Role assignments at **organization** and **repository** level (future levels stubbed).
- Predefined roles: Owner, Maintainer, Developer, Guest.
- Enforcement for repositories (Epic 3): Owner/Maintainer can create/delete repos, Developer can push/pull, Guest can read only.
- CLI/API endpoints for managing team membership and role assignment.

### Out of Scope (MVP)
- Nested teams (flat only for now).
- Fine‑grained permissions (branch protection, pipelines, artifacts).
- UI for team management (API‑only at MVP).
- External directory sync (SCIM/LDAP).
- Audit trails of role changes.

---

## Personas
- **Org Admin/Owner**: Creates teams, assigns users to repos with roles.
- **Developer**: Sees own role and permissions for repos.

---

## Architecture (Local‑First)
- Extend `auth‑svc`/`app` container with team/role tables and APIs.
- Roles enforced by middleware in `api‑gateway`.
- Database persistence in Postgres.
- For local dev, role enforcement is only checked for repositories (push/pull, repo CRUD).

---

## Data Model (SQL)
- **teams**(id uuid PK, org_id, name unique within org, created_at)
- **team_members**(team_id, user_id, created_at, role ENUM('member','maintainer'))
- **role_assignments**(id uuid PK, subject_type ENUM('user','team'), subject_id, scope_type ENUM('org','repo'), scope_id uuid, role ENUM('owner','maintainer','developer','guest'), created_at)

Indexes: team_id+user_id unique; scope_id+subject_id unique.

---

## REST API (MVP)
Base path: `/api/v1`

### Teams
- `POST /teams` → { name } ⇒ create team in org.
- `GET /teams` → list teams in org.
- `GET /teams/{id}` → details + members.
- `POST /teams/{id}/members` → { userId } ⇒ add user.
- `DELETE /teams/{id}/members/{userId}`

### Role Assignments
- `POST /roles` → { subjectType, subjectId, scopeType, scopeId, role }
- `GET /roles?scopeType=repo&scopeId=<id>` → list assignments.
- `DELETE /roles/{id}`

> Middleware consults `role_assignments` to enforce repo API + git actions.

---

## Acceptance Criteria
- Owner can create teams and assign users.
- Maintainer can add developers to repo.
- Developer can push/pull to repo; Guest can only clone.
- Enforced consistently for both HTTP Git and SSH Git.

---

## Test Plan
- Unit: role evaluator, scope checker.
- Integration: team create/list, assign roles, check enforcement on repo CRUD.
- E2E: clone repo as guest (read‑only), push as developer (succeeds), push as guest (403).

---

## Config (env)
_No new config for MVP._

---

## Future (Post‑MVP)
- Nested teams, inherited roles.
- Custom roles with granular permissions (e.g., “pipeline-runner”).
- UI management pages.
- SCIM/LDAP integration.
- Audit logs for role changes.
