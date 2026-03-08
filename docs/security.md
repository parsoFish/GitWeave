# Security

This document describes every security-sensitive surface in GitWeave and provides
operators with a pre-production checklist to verify each surface before going live.

---

## Terraform State

### State Access Control

The Terraform remote state backend stores all resource IDs, OIDC trust configurations,
team memberships, and repository settings. Anyone with read access to the state backend
effectively has read access to the full org configuration.

**Requirements:**
- The state backend (S3, GCS, or equivalent) must be restricted to the CI service
  account and designated administrators only. No public access.
- Enable bucket versioning so accidental state corruption can be rolled back.
- Enable access logging on the state bucket to detect unauthorized reads.
- Use a Terraform state lock mechanism (DynamoDB for S3 backends) to prevent
  concurrent modifications.

### State Encryption

Unencrypted state in a shared bucket exposes all org secrets and resource IDs.

**Requirements:**
- Enable server-side encryption (SSE) on the state bucket — at minimum AES-256,
  preferably AWS KMS or GCP CMEK.
- The KMS key policy must restrict decrypt access to the CI service account and
  designated administrators.
- Confirm encryption-at-rest is enforced via bucket policy; deny any `PutObject`
  request that does not include an encryption header.

---

## GITHUB_TOKEN Permissions

All workflows in this repository declare explicit `permissions` blocks to prevent
the implicit `write-all` default that GitHub Actions applies when no permissions
block is present. Each workflow and job is granted only the scopes it actually needs.

### Workflow Permissions Table

| Workflow | Job | Scope | Value | Justification |
|---|---|---|---|---|
| `ci` | (top-level) | `contents` | `read` | Checks out the repository to run structural tests and linters. No writes needed. |
| `gitweave-apply` | (top-level) | `contents` | `read` | Checks out the repository to read overlay config files. |
| `gitweave-apply` | (top-level) | `pull-requests` | `write` | Posts dry-run summaries as PR comments when triggered on pull requests. |
| `gitweave-infra` | `plan` | `contents` | `read` | Checks out infra/ code to run `terraform plan`. |
| `gitweave-infra` | `plan` | `pull-requests` | `write` | Posts Terraform plan output as a collapsible PR comment. |
| `gitweave-infra` | `apply` | `contents` | `read` | Checks out infra/ code to run `terraform apply`. |
| `gitweave-infra` | `apply` | `id-token` | `write` | Required for OIDC-based cloud provider authentication (no long-lived credentials stored). |
| `module-calver` | `validate-version` | `contents` | `read` | Reads copier.yaml files to validate CalVer format; no writes performed. |
| `module-calver` | `tag-version` | `contents` | `write` | Pushes CalVer git tags to the repository on merge to main. |
| `module-update-propagation` | (top-level) | `contents` | `write` | Pushes update branches to consumer repositories via GITHUB_TOKEN. |
| `module-update-propagation` | (top-level) | `pull-requests` | `write` | Opens pull requests in consumer repositories via `gh pr create`. |
| `overlay-validate` | (top-level) | `contents` | `read` | Reads overlay config YAML files for schema validation; no writes performed. |
| `tf-validate` | (top-level) | `contents` | `read` | Checks out infra/ code to run `terraform validate` and `terraform fmt`; no writes performed. |

### CI Enforcement

The script `scripts/check_workflow_permissions.py` runs on every pull request
via `ci.yaml`. It parses all workflow YAML files and exits non-zero if any workflow
lacks an explicit `permissions` block (either at the top level or on every individual
job). This prevents new workflows from accidentally inheriting the write-all default.

See [#permissions](#github_token-permissions) for the full permissions table.

---

## OIDC Trust Policy

The `gitweave-infra` apply job uses OIDC federation (`id-token: write`) to obtain
short-lived cloud provider credentials instead of storing long-lived service account
keys as repository secrets.

### Trust Policy Scope

An overly broad OIDC trust policy (e.g., trusting all branches or all repos) allows
any contributor-triggered workflow to acquire production cloud credentials.

**Requirements:**
- The cloud provider's OIDC trust policy must restrict the `sub` (subject) claim to
  the production environment only:
  ```
  sub: repo:<org>/<repo>:environment:production
  ```
- Do **not** use a wildcard subject claim (`*`) or trust all branches.
- Restrict to the `main` branch ref and the `production` environment — the
  apply job must reference `environment: production` in the workflow YAML.
- Audit the trust policy periodically. If the organization name or repository name
  changes, update the subject claim accordingly.

### Token Lifetime

OIDC tokens are short-lived (typically 10 minutes) and cannot be reused after
expiry. No rotation is required, but confirm the cloud provider is configured to
reject tokens with a lifetime exceeding your policy maximum.

---

## Webhook HMAC

The GitWeave metrics service receives GitHub webhook payloads for deployment events.
Without a shared HMAC secret, the service accepts payloads from any sender, making
it trivial to inject fake deployment events and corrupt DORA metrics.

### Configuration

1. Generate a strong random secret (minimum 32 bytes):
   ```bash
   openssl rand -hex 32
   ```
2. Set the secret as `WEBHOOK_SECRET` in both:
   - The GitHub repository/org webhook configuration (Settings → Webhooks → Secret).
   - The metrics service environment (GitHub Actions secret or container environment variable).
3. The metrics service validates the `X-Hub-Signature-256` header on every inbound
   request and returns HTTP 401 for payloads that fail HMAC verification.

### Webhook Secret Rotation

To rotate the webhook HMAC secret with zero downtime:

1. **Add the new secret**: Generate a new secret and add it to the metrics service
   configuration. The service should temporarily accept both the old and new secrets
   during the transition window.
2. **Deploy the updated service**: Roll out the updated metrics service so it accepts
   both secrets simultaneously. Verify the deployment is healthy before proceeding.
3. **Remove the old secret**: Update the GitHub webhook configuration to use the new
   secret only, then remove the old secret from the metrics service configuration and
   redeploy. Verify that payloads signed with the old secret are now rejected.

---

## /metrics Endpoint Authentication

The `/metrics` endpoint exposes Prometheus-format DORA metrics. An unauthenticated
endpoint leaks deployment frequency, pipeline names, and timing data to any
network-adjacent attacker.

### Configuration

1. Generate a strong bearer token (minimum 32 bytes):
   ```bash
   openssl rand -hex 32
   ```
2. Set the token as `METRICS_AUTH_TOKEN` in the metrics service environment.
3. Configure your Prometheus scrape job to pass the token as an `Authorization` header:
   ```yaml
   scrape_configs:
     - job_name: gitweave
       bearer_token: <METRICS_AUTH_TOKEN>
       static_configs:
         - targets: ['metrics-service:8080']
   ```
4. The metrics service must reject requests that omit or present an invalid
   `Authorization: Bearer <token>` header with HTTP 401.

### Metrics Auth Token Rotation (METRICS_AUTH_TOKEN)

To rotate the metrics bearer token with zero downtime:

1. **Add the new secret**: Generate a new `METRICS_AUTH_TOKEN` value and stage it
   in the service configuration (alongside the old token if the service supports
   multi-token validation).
2. **Deploy and update Prometheus**: Roll out the updated metrics service and update
   the Prometheus scrape configuration to use the new token. Verify metrics are
   still being collected before removing the old token.
3. **Remove the old secret**: Delete the old `METRICS_AUTH_TOKEN` from the service
   configuration, redeploy, and confirm that requests using the old token are
   rejected with HTTP 401.

---

## Secret Rotation

This section describes the general zero-downtime rotation process for all GitWeave
secrets. Each secret-specific section above also provides tailored steps.

### Zero-Downtime Rotation Steps

**Step 1 — Add the new secret**: Generate a new credential and add it to the service
configuration or secret store. Do not remove the old secret yet. At this point both
the old and new credentials are valid.

**Step 2 — Deploy**: Roll out the updated service or configuration that reads the
new secret. Verify the deployment is healthy and all integrations are functioning
correctly with the new secret.

**Step 3 — Remove the old secret**: Once the new secret is confirmed working,
delete the old secret from the secret store and redeploy if necessary. Verify that
requests or operations using the old credential are now rejected.

### Managed Secrets

| Secret | Location | Rotation Frequency |
|---|---|---|
| `WEBHOOK_SECRET` | GitHub repo secret + metrics service env | Every 90 days or on suspected compromise |
| `METRICS_AUTH_TOKEN` | GitHub repo secret + metrics service env | Every 90 days or on suspected compromise |
| Terraform cloud provider credentials | OIDC (no rotation needed) | N/A — short-lived tokens via OIDC |
| `GITHUB_TOKEN` | Auto-issued by GitHub Actions | N/A — expires with the workflow run |

---

## Supply Chain Hardening

### GitHub Action SHA Pinning

All `uses:` directives in `.github/workflows/*.yaml` must reference actions by their
full 40-character commit SHA, not by mutable version tags such as `@v4` or `@main`.

**Why SHA pinning?** A mutable tag (e.g., `actions/checkout@v4`) can be silently
repointed to a malicious commit after the original merge was reviewed. SHA pinning
guarantees the exact commit being executed regardless of any upstream tag changes —
this eliminates tag-hijacking as a supply-chain attack vector.

**Format:** Every pinned SHA must be accompanied by a version comment so reviewers
can identify the version without dereferencing the SHA manually:

```yaml
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

### Updating Pinned Actions

When a new version of an action is released:
1. Look up the commit SHA for the new tag (e.g., via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`).
2. Update the workflow file with the new SHA and version comment.
3. Open a pull request — the CI `check_workflow_permissions.py` and structural tests
   will verify the update is complete.

### Dependabot for Action Updates

Consider enabling GitHub Dependabot for GitHub Actions in `.github/dependabot.yaml`
to receive automated PRs when new action versions are released. Dependabot preserves
SHA pinning when updating.

---

## Pre-Production Checklist

Before deploying GitWeave to a production environment, verify all of the following.
Check each item off (`- [x]`) and record the reviewer's name and date.

### Infrastructure

- [ ] Terraform remote state backend is configured (not local state).
- [ ] Terraform state is encrypted at rest (SSE/KMS enabled on the state bucket).
- [ ] Terraform state access is restricted to the CI service account and designated admins only.
- [ ] State bucket versioning is enabled for rollback capability.
- [ ] State locking is enabled (e.g., DynamoDB lock table for S3 backends).

### OIDC Trust Policy

- [ ] OIDC trust policy subject claim is scoped to the `production` environment only (not a wildcard).
- [ ] The `gitweave-infra` apply job references `environment: production` in the workflow.
- [ ] No long-lived cloud provider credentials are stored as repository secrets.

### GitHub Token Scopes

- [ ] All workflows declare explicit `permissions` blocks (verified by `check_workflow_permissions.py`).
- [ ] No workflow grants broader scopes than required (see [Workflow Permissions Table](#workflow-permissions-table)).

### Webhook HMAC

- [ ] `WEBHOOK_SECRET` is set in the GitHub webhook configuration.
- [ ] `WEBHOOK_SECRET` is set as a GitHub Actions secret or container environment variable.
- [ ] The metrics service validates `X-Hub-Signature-256` on every inbound request.
- [ ] Webhook secret rotation procedure has been reviewed and is documented for the ops team.

### /metrics Endpoint Authentication

- [ ] `METRICS_AUTH_TOKEN` is set in the metrics service environment.
- [ ] The `/metrics` endpoint rejects unauthenticated requests with HTTP 401.
- [ ] Prometheus scrape configuration includes the bearer token header.
- [ ] Metrics auth token rotation procedure has been reviewed and documented for the ops team.

### Supply Chain

- [ ] All GitHub Actions in `.github/workflows/` are pinned to full commit SHAs (not tags).
- [ ] Every SHA pin has a version comment (e.g., `# v4.2.2`) on the same line.
- [ ] Dependabot (or equivalent) is configured to notify when pinned action versions are updated.

### Secrets Hygiene

- [ ] No secrets are hardcoded in source code, workflow files, or configuration files.
- [ ] All required secrets are documented in this file and in the team runbook.
- [ ] Secret rotation schedule is established (minimum every 90 days for long-lived secrets).
