# Data Model: Control Repository

**Feature**: 001-control-repo-structure

## Entities

### 1. Control Repository (Root)
The root of the GitWeave platform. It is a Monorepo containing all configuration, infrastructure, and templates.

**Structure**:
- `modules/`: Collection of Template Modules.
- `config/`: Collection of Overlay Configurations.
- `infra/`: Infrastructure as Code (Terraform).
- `metrics/`: Source code for the Metrics Observer.
- `.github/workflows/`: CI/CD definitions.

### 2. Template Module
A reusable unit of configuration or code, located in `modules/<module-name>`.

**Fields**:
- `name`: Directory name (e.g., `lang-node`).
- `content`: Files inside the directory.

### 3. Overlay Configuration
A configuration file applying policy or settings, located in `config/`.

**Fields**:
- `path`: File path (e.g., `config/org-policy.yaml`).
- `content`: YAML/JSON content.

### 4. Infrastructure Component
A Terraform root module located in `infra/`.

**Fields**:
- `main.tf`: Entry point.
- `variables.tf`: Inputs.
- `outputs.tf`: Outputs.
