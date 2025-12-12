# Quickstart: Bootstrapping the Control Repo

**Feature**: 001-control-repo-structure

## Prerequisites

- A GitHub Organization.
- A Cloud Provider account (AWS/Azure/GCP) for Terraform state (optional but recommended).
- `git`, `terraform`, and `python3` installed locally.

## Bootstrap Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/YOUR_ORG/gitweave-control.git
   cd gitweave-control
   ```

2. **Initialize Infrastructure**
   Navigate to the `infra/` directory.
   ```bash
   cd infra
   ```
   **Important**: You must configure your Terraform backend (S3, GCS, Azure, Terraform Cloud) in `main.tf` or a separate `backend.tf` file before proceeding.
   ```bash
   terraform init
   terraform apply
   ```
   This sets up the baseline organization settings and OIDC trust.

3. **Push to GitHub**
   Commit the initial structure and push.
   ```bash
   git add .
   git commit -m "chore: bootstrap control repo structure"
   git push origin main
   ```

4. **Verify Workflows**
   Go to the "Actions" tab in your GitHub repository. You should see `gitweave-infra` and `gitweave-apply` workflows. They might skip if no changes were detected in their paths, or fail if secrets are missing.

## Adding a Module

1. Create a directory in `modules/`:
   ```bash
   mkdir -p modules/my-template
   echo "# My Template" > modules/my-template/README.md
   ```

2. Commit and push.

## Adding Configuration

1. Create a file in `config/`:
   ```bash
   echo "policy: enabled" > config/policy.yaml
   ```

2. Commit and push. The `gitweave-apply` workflow will trigger.
