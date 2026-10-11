# Work-item decomposition — INIT-2026-10-11-i2-apply-engine-terraform-retired

14 work item(s) emitted.

## Top-level scope (eyeball for off-target dirs)
- `tests/` — 22 file ref(s)
- `gitweave/` — 13 file ref(s)
- `infra/` — 7 file ref(s)
- `.github/` — 3 file ref(s)
- `schemas/` — 3 file ref(s)
- `config/` — 2 file ref(s)
- `pyproject.toml/` — 1 file ref(s)
- `README.md/` — 1 file ref(s)
- `docs/` — 1 file ref(s)
- `scripts/` — 1 file ref(s)

## WI-1
- pyproject.toml
- gitweave/__init__.py
- gitweave/cli.py
- tests/test_package_structure.py

## WI-10
- .github/workflows/gitweave-apply.yaml
- tests/test_apply_workflow_structure.py
- tests/test_gw_apply_workflow.py

## WI-11
- README.md
- docs/demo-guide.md
- tests/test_docs_terraform_retired.py

## WI-12
- tests/acceptance/__init__.py
- tests/acceptance/test_gw_workflow.py

## WI-2
- gitweave/auth.py
- tests/test_auth.py

## WI-3
- schemas/org.schema.json
- schemas/teams.schema.json
- schemas/org-ruleset.schema.json
- config/org.yaml
- config/rulesets.yaml
- tests/fixtures/org-empty.json
- tests/test_gw_schemas.py

## WI-4
- gitweave/config.py
- tests/test_config.py

## WI-5a
- gitweave/managers/__init__.py
- gitweave/managers/org.py
- tests/test_manager_org.py

## WI-5b
- gitweave/managers/teams.py
- gitweave/managers/repos.py
- gitweave/managers/rulesets.py
- tests/test_manager_resources.py

## WI-6
- gitweave/plan.py
- tests/test_plan.py

## WI-7
- gitweave/apply.py
- gitweave/reset.py
- tests/test_apply_reset.py

## WI-8
- gitweave/cli.py
- tests/test_cli.py

## WI-9a
- infra/branch_protection.tf
- infra/main.tf
- infra/outputs.tf
- infra/variables.tf
- infra/examples/branch_protection_override.tfvars
- infra/demo.tfvars.example
- infra/bootstrap/README.md
- .github/workflows/gitweave-infra.yaml
- tests/test_tf_teams_structure.py
- tests/test_tf_teams_validate.py
- tests/test_tf_teams_plan.py
- tests/test_terraform_demo_config.py
- tests/test_infra_workflow_gates.py
- tests/test_structure.py
- scripts/bootstrap.sh
- .github/workflows/ci.yaml

## WI-9b
- tests/test_gw_teams.py
