# Research: Control Repository Structure

**Feature**: 001-control-repo-structure
**Date**: 2025-12-13

## Decisions

### 1. Metrics Service Language
- **Decision**: Python
- **Rationale**:
  - **Maintainability**: The primary maintainer is familiar with Python, reducing the barrier to entry and maintenance cost.
  - **Ecosystem**: Python has excellent libraries for API interaction (e.g., `requests`, `boto3`) and metrics (Prometheus client).
  - **Performance**: For a control-plane observer (not a high-throughput data plane proxy), Python's performance is sufficient.
- **Alternatives Considered**:
  - **Go (Golang)**: Originally considered as it is the industry standard for cloud-native observability (Prometheus/OpenTelemetry). It offers single-binary distribution and higher concurrency. However, the learning curve and context switching costs for the team outweigh these benefits for this specific component.

### 2. Terraform Bootstrap Strategy
- **Decision**: Out-of-Band State Configuration (Bring Your Own Backend).
- **Rationale**:
  - **Flexibility**: Platform engineers have diverse preferences (S3, GCS, Azure Blob, Terraform Cloud) and existing standards. Prescribing a specific "bootstrap" bucket creation flow is overly opinionated and brittle.
  - **Simplicity**: Reduces the complexity of the initial setup script.
  - **Local Dev**: Local state remains the default for testing and development, ensuring `gw:plan` (local reproducibility) works out of the box.
- **Alternatives Considered**:
  - **Two-Stage Bootstrap**: Originally considered to automate bucket creation. Rejected because it assumes too much about the cloud provider and permissions.
  - **Terraform Cloud**: Good option, but we want to support generic backends.

### 3. Workflow Structure
- **Decision**: Split workflows by concern (`infra` vs `config`).
- **Rationale**:
  - `gitweave-infra.yaml`: Runs Terraform. High privilege, infrequent changes.
  - `gitweave-apply.yaml`: Runs Config application (GitWeave logic). Lower privilege (maybe), frequent changes.
  - Path filtering (`on.push.paths`) ensures we don't run Terraform when only changing a template.

## Open Questions Resolved

- **Q**: What specific resources go into `infra/` initially?
- **A**: The `infra/` directory will contain the "Organization Baseline". This includes:
  - The State Bucket (if self-managed).
  - GitHub Organization Settings (via `integrations/github` provider).
  - Branch Protection Rules for the Control Repo itself.
  - OIDC Trust for GitHub Actions (to talk to AWS/Azure/GCP).

- **Q**: What is the "Bootstrap" process?
- **A**:
  1. Clone repo.
  2. Run `scripts/bootstrap.sh` to verify prerequisites and directory structure.
  3. User configures their preferred Terraform backend in `infra/` (or uses local state for testing).
  4. User runs `terraform init` and `terraform apply` to set up the org baseline.
  5. Script pushes initial commit to GitHub.
