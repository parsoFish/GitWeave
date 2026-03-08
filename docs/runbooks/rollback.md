# Rollback Runbook

This runbook covers how to recover from a bad overlay apply or Terraform apply.
Follow the relevant section based on the type of change that needs reverting.

---

## Overlay Rollback

Use this procedure when a bad config overlay has been applied to one or more repos.

### Steps

**1. Identify the bad commit**

```bash
git log --oneline config/
```

**2. Revert the bad commit**

Create a revert commit so the change is preserved in history:

```bash
git revert <commit-sha>
```

If the bad change spans multiple commits, revert the range:

```bash
git revert <oldest-sha>..<newest-sha>
```

**3. Push the revert to the main branch**

```bash
git push origin main
```

This triggers the GitWeave Apply workflow automatically (it watches `config/**` on `main`).

**4. Re-apply overlays (manual trigger)**

If an immediate re-apply is required without waiting for CI, trigger the workflow directly:

```bash
gh workflow run gitweave-apply.yaml --ref main
```

Or re-run the apply script locally with the target environment:

```bash
python scripts/apply-overlays.py --env staging --config-dir config/repos/
python scripts/apply-overlays.py --env production --config-dir config/repos/
```

**5. Confirm apply succeeded**

Check the most recent workflow run:

```bash
gh run list --workflow=gitweave-apply.yaml --limit 5
gh run view <run-id>
```

---

## Terraform Rollback

Use this procedure when a Terraform apply has produced undesired infrastructure changes.

### When to use each approach

| Scenario | Command |
|---|---|
| A resource was created by mistake and should be removed from state | `terraform state rm` |
| State file drifted from reality (e.g. manual changes outside Terraform) | `terraform state pull` + edit + `terraform state push` |
| Roll back to a previous state snapshot | restore from remote state backend version, then `terraform apply` |
| Revert infrastructure to match a prior config commit | `git revert` the infra change, then re-run `terraform apply` |

### Procedure

**1. Review the current state**

```bash
cd infra
terraform state list
terraform state show <resource.name>
```

**2. Use `terraform state rm` to remove incorrectly created resources**

Use when a resource was accidentally created and needs to be dropped from state
without destroying the real cloud resource:

```bash
terraform state rm <resource.address>
```

**3. Use `terraform state pull` to inspect or repair drifted state**

Use when you need to examine or manually correct the raw state JSON:

```bash
terraform state pull > tfstate-backup.json
# edit tfstate-backup.json as needed
terraform state push tfstate-backup.json
```

**4. Revert infra config and re-apply**

When the Terraform configuration itself is wrong, prefer reverting the HCL change
and re-applying over manual state surgery:

```bash
git revert <bad-infra-commit>
git push origin main
```

Then wait for the GitWeave Infrastructure workflow to run, or trigger it manually:

```bash
gh workflow run gitweave-infra.yaml --ref main
```

> **Caution:** Review the plan output carefully before applying. Never use
> `-auto-approve` without first inspecting `terraform plan` output.

---

## Post-Incident Verification

After completing a rollback, confirm the system is in the expected state.

### Verify overlay apply

Check that the apply workflow succeeded and all repos received the correct overlays:

```bash
gh run list --workflow=gitweave-apply.yaml --limit 3
gh run view <run-id> --log
```

Validate overlay configs are still valid:

```bash
python scripts/validate_overlay_configs.py --config-dir config/repos/
```

### Verify Terraform state

Confirm infrastructure matches the expected Terraform config:

```bash
cd infra
terraform plan -input=false
```

A clean plan should report "No changes. Infrastructure is up-to-date."

### Verify metrics endpoint (if applicable)

```bash
curl -sf http://localhost:8000/health || echo "Health check failed"
```

### Close the incident

Once the system is verified, close the incident issue:

```bash
gh issue list --label "incident,workflow-failure" --state open
gh issue close <issue-number> --comment "Resolved: rollback successful, system verified."
```
