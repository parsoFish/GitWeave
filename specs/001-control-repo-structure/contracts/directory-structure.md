# Contract: Directory Structure

**Feature**: 001-control-repo-structure

## Root Directory Layout

The Control Repository MUST adhere to the following structure.

```text
/
├── .github/
│   └── workflows/
│       ├── gitweave-apply.yaml  # Triggered on config/** changes
│       └── gitweave-infra.yaml  # Triggered on infra/** changes
├── config/                      # Overlay Configuration (YAML)
│   └── [files]
├── infra/                       # Terraform Bootstrap
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── metrics/                     # Metrics Observer Service
│   ├── requirements.txt
│   ├── src/
│   │   └── main.py
│   └── ...
├── modules/                     # Template Modules
│   ├── [module-name]/
│   │   └── ...
└── README.md                    # Bootstrap Documentation
```

## Constraints

1. **`modules/`**: MUST be a flat list of directories (or categorized subdirectories).
2. **`config/`**: MUST contain valid YAML/JSON configuration files.
3. **`infra/`**: MUST contain valid Terraform configuration.
4. **`metrics/`**: MUST contain a valid Python project (requirements.txt or pyproject.toml).
