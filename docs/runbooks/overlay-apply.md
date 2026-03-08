# Overlay Apply Runbook

This runbook documents the GitWeave overlay apply pipeline, covering the
staging → production promotion flow, reviewer approval requirements, and
rollback procedures for failed applies.

## Overview

The `gitweave-apply` workflow applies Copier overlay configurations from
`config/repos/` to target repositories. It runs in two sequential stages:

1. **Staging** (`apply-staging` job) — applies overlays that declare
   `spec.environments.staging` to staging-environment repos.
2. **Production** (`apply-production` job) — applies overlays that declare
   `spec.environments.production` to production repos. This job only starts
   after staging succeeds and requires reviewer approval.

## Promotion Flow: Staging → Production

Changes are promoted from staging to production automatically when:

1. The `apply-staging` job completes successfully.
2. A required reviewer approves the `production` environment deployment in
   the GitHub UI or API.
3. The `apply-production` job then runs, applying production-scoped overlays.

**To trigger a manual promotion:**
```bash
gh workflow run gitweave-apply.yaml -f target_env=staging   # staging only
gh workflow run gitweave-apply.yaml -f dry_run=true         # dry-run both
```

## Reviewer Approval

The `apply-production` job references `environment: production`, which
enforces GitHub's environment protection rules. Before the production job
starts, all required reviewers listed in the `production` environment settings
must approve the deployment.

To configure reviewers:
1. Go to **Settings → Environments → production** in the repository.
2. Add required reviewers under **Required reviewers**.
3. GitHub will block `apply-production` until at least one reviewer approves.

## Environment Filtering

The script uses `spec.environments` in each overlay config to determine which
repos belong to each environment:

```yaml
spec:
  environments:
    staging:
      variables:
        LOG_LEVEL: info
    production:
      variables:
        LOG_LEVEL: error
```

- `--env staging` → only overlays with `spec.environments.staging` are applied.
- `--env production` → only overlays with `spec.environments.production` are applied.
- No `--env` flag → all overlays are applied (backward-compatible).

## Rollback and Recovery

If an apply fails or a bad overlay is merged:

### Revert the config change
```bash
git revert <commit-sha>  # revert the bad overlay config
git push origin main
```

### Fix the overlay and re-run
1. Correct the overlay YAML in `config/repos/`.
2. Push to a branch and open a PR.
3. The PR triggers a dry-run so you can review the diff before merging.

### Close a bad PR in a target repo
If the overlay already opened a PR in a target repository:
```bash
gh pr close <number> --repo <org/repo> --comment "Reverting bad overlay apply"
```

### Emergency: skip staging gate
In rare cases where staging must be skipped (e.g. staging environment is
degraded), you can trigger the script directly:
```bash
GITHUB_TOKEN=<token> python scripts/apply-overlays.py \
  --env production --config-dir config/repos/
```
Always document the reason and follow up with a normal promotion cycle.

## Monitoring

- Check the **Actions** tab for workflow run status.
- Failed jobs show in red; click the job to see the step that failed.
- The dry-run step on PRs posts a comment with the diff — review it before merging.
