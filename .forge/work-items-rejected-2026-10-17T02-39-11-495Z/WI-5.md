---
work_item_id: WI-5
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on: []
domain: schema
acceptance_criteria:
  - given: "an overlay config with spec.modules: [{name: python_service, version: '2026.10.1', inputs: {service_name: foo}}]"
    when: "jsonschema validates it against schemas/overlay.schema.json"
    then: "validation passes without errors"
  - given: "config/policy.yaml with per-team allowed_modules: [python_service] and a second team with allowed_modules: [terraform_module]"
    when: "PolicyLoader().load() runs"
    then: "the loaded policy object exposes per-team allowed_modules; an invalid policy.yaml fails at load time with a schema error"
  - given: "config/policy.yaml is absent"
    when: "PolicyLoader().load() runs"
    then: "raises a named PolicyError (not FileNotFoundError); the error message names the policy rule"
  - given: "schemas/policy.schema.json is a valid JSON Schema document"
    when: "jsonschema validates config/policy.yaml against it"
    then: "validation passes"
files_in_scope:
  - schemas/overlay.schema.json
  - schemas/policy.schema.json
  - gitweave/policy.py
  - config/policy.yaml
  - tests/test_overlay_schema.py
  - tests/test_policy_overlay.py
creates:
  - schemas/policy.schema.json
  - tests/test_policy_overlay.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_policy_overlay.py::TestPolicyOverlay::test_allowed_modules_loaded"
  - "-p"
  - "no:cacheprovider"
---

# WI-5: Overlay schema spec.modules + policy schema allowed_modules

Target: extend `schemas/overlay.schema.json`, create `schemas/policy.schema.json`, extend `gitweave/policy.py`, extend `config/policy.yaml`.

## schemas/overlay.schema.json extension

Add a `spec.modules` array to the overlay entry schema. Each module entry:

```json
{
  "type": "object",
  "required": ["name", "version", "inputs"],
  "additionalProperties": false,
  "properties": {
    "name": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_]*$",
      "description": "Snake-case module name matching modules/<name>/ directory"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d{4}\\.\\d+\\.\\d+$",
      "description": "CalVer version string"
    },
    "inputs": {
      "type": "object",
      "description": "Copier question answers for this module"
    }
  }
}
```

The `spec.modules` field is optional (some repos have no overlay modules).

## schemas/policy.schema.json (new)

Create a JSON Schema for `config/policy.yaml`. Key structure:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "teams": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "allowed_modules": {
            "type": "array",
            "items": {"type": "string"}
          },
          "allowed_repos": {"type": "array", "items": {"type": "string"}},
          "allowed_exceptions": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

## gitweave/policy.py extensions

1. **Schema validation at load time**: `PolicyLoader.load()` validates `config/policy.yaml` against `schemas/policy.schema.json` using jsonschema. An invalid policy fails immediately with a descriptive error (not `FileNotFoundError`).

2. **Absent policy.yaml → fail closed**: If `config/policy.yaml` does not exist, raise `PolicyError` with message naming the rule (e.g. `"policy-absent: config/policy.yaml is required; refusing request"`). Never raise bare `FileNotFoundError`.

3. **allowed_modules access**: Add `policy.allowed_modules_for_team(team_slug: str) -> list[str]` returning the team's allowed module names (empty list if team not in policy or key absent).

## config/policy.yaml extension

Extend the existing file to add `allowed_modules` under at least one team entry:

```yaml
teams:
  example-team:
    allowed_modules:
      - python_service
    # ... existing fields ...
  restricted-team:
    allowed_modules: []
    # ... existing fields ...
```

## tests/test_overlay_schema.py

Add new test methods to the existing test class:
- `test_spec_modules_valid_entry_passes` — validates a full modules entry
- `test_spec_modules_invalid_name_fails` — rejects camelCase name
- `test_spec_modules_version_calver_required` — rejects non-CalVer version

## tests/test_policy_overlay.py (new)

Class `TestPolicyOverlay`:
- `test_allowed_modules_loaded` — loads policy, asserts `allowed_modules_for_team("example-team")` returns the declared list
- `test_policy_absent_raises_policy_error` — removes/patches policy file path, asserts `PolicyError` raised (not `FileNotFoundError`)
- `test_invalid_policy_yaml_raises_at_load` — patches policy content to be schema-invalid, asserts error at load
- `test_team_not_in_policy_returns_empty` — asserts `allowed_modules_for_team("unknown")` returns `[]`

Tests must NOT inherit any GW_* autouse fixture.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
