# GitWeave

**GitWeave** is a single "control" repository that configures and weaves together a GitHub organisation using in-repo modules, overlays, and provider-native tooling.

Instead of building a heavy standalone platform, GitWeave overlays your GitHub organization to provide standardized templates, governance, and observability while leveraging GitHub's native strengths (Actions, Issues, Packages).

## 🚀 Vision

*   **Control Repo Centricity**: Run your entire platform from one core repo.
*   **Provider-Native**: Use GitHub for hosting, CI, Identity, and Work Management.
*   **Platform as Code**: Define behavior via configuration and Terraform, not bespoke services.
*   **Greenfield & Brownfield**: Bootstrap new orgs or safely overlay existing ones.

## 🛠️ SpecKit Workspace

This repository is a **SpecKit Workspace**. We use [SpecKit](https://github.com/github/spec-kit) to drive development through structured specifications and AI-assisted planning.

### Workflow
1.  **Constitution**: Defines the non-negotiable principles (see below).
2.  **Specify**: Use `/speckit.specify` to define features (e.g., "Create a Node.js Template Module").
3.  **Plan**: Use `/speckit.plan` to generate technical implementation plans.
4.  **Implement**: Use `/speckit.implement` to drive code generation.

All specs live in `specs/`, and the project governance is defined in `.specify/memory/constitution.md`.

## 📜 Constitution & Governance

Our [Constitution](.specify/memory/constitution.md) defines the core rules of engagement. Key highlights:

*   **Control Repo Centricity**: All behavior drives from this repo.
*   **Provider-Native First**: Don't re-invent the wheel (use Actions, Issues, Packages).
*   **Platform as Code**: Terraform is the standard for infra; Actions for orchestration.
*   **Local Reproducibility**: CLI tools must support local dry-runs (`gw:plan`).
*   **Observability**: DORA metrics via Prometheus/OpenTelemetry standards.

## 🧩 Core Concepts

### Control Repository
The heart of GitWeave. It holds:
*   **Specs**: SpecKit definitions for the org and modules.
*   **Terraform**: Modules for provisioning GitHub resources and cloud infra.
*   **Workflows**: GitHub Actions to apply configuration.
*   **Overlay Config**: Tracks which templates apply to which managed repos.

### Template Modules
Composable building blocks stored in `modules/` (e.g., `modules/lang-node`, `modules/workflows/ci-basic`).
*   **DRY**: Reused across many repos.
*   **Composable**: Mix-and-match (e.g., Node.js Starter + AWS Infra + DORA Metrics).
*   **In-Repo**: No need for separate template repositories.

### Managed Repositories
The application or library repos that GitWeave manages.
*   **Overlay Config**: Each repo has an entry in `config/repos/` defining its applied modules and environments.
*   **No Lock-in**: GitWeave manages config/workflows; the code remains standard Git.

### Metrics Aggregator
A lightweight component (Service or Workflow) that:
*   Ingests GitHub events (commits, deployments).
*   Computes DORA metrics (Lead Time, Deployment Frequency).
*   Exposes data in Prometheus/OpenTelemetry format.

## 🔄 Usage Modes

### 1. Greenfield Org (Bootstrap)
*   Clone this control repo into a new GitHub Org.
*   Configure provider binding (GitHub App/PAT).
*   Run bootstrap workflow to create initial teams and repos.

### 2. Existing Org (Overlay)
*   Clone control repo into existing Org.
*   Register existing repos via Overlay Config.
*   Run workflows to apply policies and standard workflows safely.

## 🤖 Automation Model

*   **GitHub Actions**: The primary orchestrator for applying changes.
*   **Terraform**: The engine for stateful infrastructure (repos, teams, cloud resources).
*   **Docker (Optional)**: Only used for rich dashboards or long-running aggregators if Actions are insufficient.

## 📂 Project Structure

```text
.
├── .github/
│   └── workflows/
│       ├── gitweave-apply.yaml  # Applies config/ changes
│       └── gitweave-infra.yaml  # Applies infra/ changes
├── config/                      # Overlay Configuration (YAML)
├── infra/                       # Terraform Bootstrap (Org Baseline)
├── metrics/                     # Metrics Observer Service (Python)
├── modules/                     # Template Modules
├── scripts/                     # Helper scripts
├── specs/                       # Feature specifications (SpecKit)
├── .specify/                    # SpecKit configuration
└── README.md                    # This file

```

## 🚀 Bootstrap

To initialize a new GitWeave Control Repository:

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/YOUR_ORG/gitweave-control.git
    cd gitweave-control
    ```

2.  **Run Bootstrap Script**
    This script initializes the local environment and checks prerequisites.
    ```bash
    ./scripts/bootstrap.sh
    ```

3.  **Initialize Infrastructure**
    Navigate to `infra/` to set up the organization baseline.
    **Note**: You must configure your remote state backend (S3, GCS, etc.) in `main.tf` or `backend.tf` before running this in production. For local testing, you can skip backend configuration.
    **Auth**: Ensure `GITHUB_TOKEN` is set or you are logged in via `gh auth login` so Terraform can manage the organization.
    ```bash
    cd infra
    terraform init
    terraform apply
    ```

4.  **Push to GitHub**
    ```bash
    git add .
    git commit -m "chore: bootstrap control repo"
    git push origin main
    ```

5.  **Verify Workflows**
    Check the "Actions" tab in GitHub to ensure `gitweave-infra` and `gitweave-apply` are running correctly.

## Self-Hosting

GitWeave manages its own control repository through its overlay system — eating its own dog food.

The overlay config at `config/repos/gitweave.yaml` applies GitWeave modules and branch protection to the GitWeave control repository itself (`gitweave-io/GitWeave`). This proves the system works end-to-end and serves as a live reference implementation.

### What the self-hosting overlay configures

- **Module**: applies the `python-service` module to keep the repository's Python tooling consistent
- **Branch protection** (`main` environment): requires 1 PR review and CI status checks before merging
- **Team ownership**: the `platform` team declared in `config/teams.yaml` owns this repository

### Running the self-hosting overlay

Dry-run (no changes applied, no credentials needed):

```bash
python scripts/apply-overlays.py --dry-run
```

Apply for real (requires `GITHUB_TOKEN` with repo admin scope):

```bash
python scripts/apply-overlays.py
```

Validate schema compliance:

```bash
python scripts/validate_overlay_configs.py --config-dir config/repos/

```
