---
work_item_id: WI-2
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on: []
domain: modules
acceptance_criteria:
  - given: "modules/python_service/copier.yaml and modules/terraform_module/copier.yaml"
    when: "jsonschema validates each against schemas/copier-module.schema.json"
    then: "both validate without errors; each has a CalVer version, snake_case name matching its directory, and at least one input that changes rendered output"
  - given: "each module's template directory"
    when: "the rendered CI workflow file is checked with yamllint"
    then: "yamllint exits zero on the rendered output"
  - given: "pyproject.toml"
    when: "grep runs for copier in dependencies"
    then: "copier>=X.Y is listed in project.dependencies; requirements.txt pins the same version with a format-stability note comment"
  - given: "config/repos/example.yaml"
    when: "it is parsed"
    then: "it references python_service or terraform_module (not example-template); the CI smoke fixture continues to pass"
files_in_scope:
  - modules/python_service/copier.yaml
  - modules/python_service/.github/workflows/ci.yml.jinja
  - modules/python_service/{{ repo_name }}/.gitkeep
  - modules/terraform_module/copier.yaml
  - modules/terraform_module/.github/workflows/ci.yml.jinja
  - modules/terraform_module/terraform/main.tf.jinja
  - pyproject.toml
  - requirements.txt
  - config/repos/example.yaml
  - tests/test_copier_modules.py
creates:
  - modules/python_service/copier.yaml
  - modules/python_service/.github/workflows/ci.yml.jinja
  - modules/terraform_module/copier.yaml
  - modules/terraform_module/.github/workflows/ci.yml.jinja
  - modules/terraform_module/terraform/main.tf.jinja
  - tests/test_copier_modules.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_copier_modules.py::TestCopierModules::test_copier_yaml_validates_against_schema"
  - "-p"
  - "no:cacheprovider"
---

# WI-2: Copier modules — python_service + terraform_module

Target: create two real Copier template modules under `modules/` and wire pyproject.toml.

## Module naming

Module directory names equal their snake_case `_metadata.name`:
- `modules/python_service/` — name: `python_service`
- `modules/terraform_module/` — name: `terraform_module`

The overlay `spec.modules[].name` and the answers-file path use the same name.

## copier.yaml format

Each `copier.yaml` must validate against `schemas/copier-module.schema.json`.
Required fields (from schema):
- `_metadata.name`: snake_case, matches directory name
- `_metadata.version`: CalVer (e.g. `2026.10.1`)
- `_metadata.min_copier_version`: minimum Copier version string (e.g. `"9.0.0"`)
- At least one question that changes rendered output

### modules/python_service/copier.yaml example shape

```yaml
_metadata:
  name: python_service
  version: "2026.10.1"
  min_copier_version: "9.0.0"
  description: "Standard Python service module"

service_name:
  type: str
  help: "Snake-case name of the service"
  default: my_service

python_version:
  type: str
  help: "Python version to target"
  default: "3.11"
  choices: ["3.11", "3.12"]
```

### Template files for python_service

Create `.github/workflows/ci.yml.jinja` that renders a working GitHub Actions CI workflow using `{{ service_name }}` and `{{ python_version }}` in the rendered output. The rendered YAML must pass `yamllint`.

### modules/terraform_module/copier.yaml example shape

```yaml
_metadata:
  name: terraform_module
  version: "2026.10.1"
  min_copier_version: "9.0.0"
  description: "Standard Terraform module skeleton"

module_name:
  type: str
  help: "Snake-case name of the Terraform module"
  default: my_module

provider_version:
  type: str
  help: "Minimum required Terraform provider version"
  default: "~> 5.0"
```

### Template files for terraform_module

- `.github/workflows/ci.yml.jinja` — CI workflow for a Terraform module (using `{{ module_name }}`)
- `terraform/main.tf.jinja` — skeleton `terraform {}` block + provider block using `{{ module_name }}` and `{{ provider_version }}`

Note: GitWeave's own docs guard (`tests/test_docs_no_terraform_tokens.py`) must NOT scan `modules/` — WI-10 or ralph should narrow that guard's scope if needed. The module may contain Terraform per operator ruling R69.

## Copier dependency

Add to `pyproject.toml` `[project] dependencies`:
```
"copier>=9.0",
```

Pin in `requirements.txt`:
```
copier==9.3.1  # I4: pinned for .copier-answers.yml format stability; I5 three-way reconcile depends on this format
```

(Verify the actual latest stable Copier version and use that; document the format-stability note as shown.)

## Retire example-template

Update `config/repos/example.yaml` to reference `python_service` (or `terraform_module`) instead of `example-template`. The CI smoke fixture (`tests/test_copier_schema.py` or similar) should continue to pass.

The `modules/.gitkeep` file is removed (the directory now has real content).

## Test file: tests/test_copier_modules.py

Create `tests/test_copier_modules.py` with class `TestCopierModules`:

```python
class TestCopierModules(unittest.TestCase):
    def test_copier_yaml_validates_against_schema(self):
        """Both module copier.yaml files must validate against copier-module.schema.json."""
        ...

    def test_python_service_has_input_that_changes_output(self):
        """python_service module has >=1 input declared."""
        ...

    def test_terraform_module_has_input_that_changes_output(self):
        """terraform_module has >=1 input declared."""
        ...

    def test_module_names_match_directories(self):
        """_metadata.name matches the directory name for each module."""
        ...
```

These tests do NOT invoke Copier (offline schema validation only). The render test is WI-3.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
