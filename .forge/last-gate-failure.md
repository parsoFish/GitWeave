# Live quality-gate failure — AUTHORITATIVE (forge merge-boundary full-suite gate: local)

This is the result of the orchestrator's OWN gate run at the develop flow's merge
boundary — the full-suite gate that decides whether the PR can open (R4-10-F2). It runs
the WHOLE suite on the integrated branch tip, so it catches a cross-WI regression the
scoped per-WI gates structurally cannot see. Forge deletes this file on every passing
gate run and at session start, so if you are reading it, it is FRESH. Fix exactly what
is below; the initiative is NOT review-ready until the full suite is green.

## Failing gate (local)

```
$ python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero
"""
>       self.assertTrue(
            os.path.isfile(EXAMPLE_MODULE_COPIER_YAML),
            f"modules/example-template/copier.yaml is missing — expected at "
            f"{EXAMPLE_MODULE_COPIER_YAML}",
        )
E       AssertionError: False is not true : modules/example-template/copier.yaml is missing — expected at /home/parso/forge/_worktrees/INIT-2026-10-10-i1-honest-baseline/modules/example-template/copier.yaml

tests/test_copier_schema.py:446: AssertionError
_ TestExampleTemplateModuleIntegration.test_example_template_copier_yaml_is_parseable_yaml _

self = <test_copier_schema.TestExampleTemplateModuleIntegration testMethod=test_example_template_copier_yaml_is_parseable_yaml>

    def test_example_template_copier_yaml_is_parseable_yaml(self):
        """modules/example-template/copier.yaml must parse as a YAML mapping."""
>       with open(EXAMPLE_MODULE_COPIER_YAML) as f:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       FileNotFoundError: [Errno 2] No such file or directory: '/home/parso/forge/_worktrees/INIT-2026-10-10-i1-honest-baseline/modules/example-template/copier.yaml'

tests/test_copier_schema.py:454: FileNotFoundError
_ TestExampleTemplateModuleIntegration.test_example_template_copier_yaml_passes_schema_validation _

self = <test_copier_schema.TestExampleTemplateModuleIntegration testMethod=test_example_template_copier_yaml_passes_schema_validation>

    def test_example_template_copier_yaml_passes_schema_validation(self):
        """modules/example-template/copier.yaml must satisfy the full JSON Schema."""
>       with open(EXAMPLE_MODULE_COPIER_YAML) as f:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       FileNotFoundError: [Errno 2] No such file or directory: '/home/parso/forge/_worktrees/INIT-2026-10-10-i1-honest-baseline/modules/example-template/copier.yaml'

tests/test_copier_schema.py:464: FileNotFoundError
_ TestExampleTemplateModuleIntegration.test_example_template_name_follows_snake_case _

self = <test_copier_schema.TestExampleTemplateModuleIntegration testMethod=test_example_template_name_follows_snake_case>

    def test_example_template_name_follows_snake_case(self):
        """The name in the example module must match the snake_case pattern."""
>       with open(EXAMPLE_MODULE_COPIER_YAML) as f:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       FileNotFoundError: [Errno 2] No such file or directory: '/home/parso/forge/_worktrees/INIT-2026-10-10-i1-honest-baseline/modules/example-template/copier.yaml'

tests/test_copier_schema.py:470: FileNotFoundError
_ TestExampleTemplateModuleIntegration.test_example_template_version_follows_calver _

self = <test_copier_schema.TestExampleTemplateModuleIntegration testMethod=test_example_template_version_follows_calver>

    def test_example_template_version_follows_calver(self):
        """The version in the example module must match the CalVer YYYYMMDD.Patch pattern."""
>       with open(EXAMPLE_MODULE_COPIER_YAML) as f:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       FileNotFoundError: [Errno 2] No such file or directory: '/home/parso/forge/_worktrees/INIT-2026-10-10-i1-honest-baseline/modules/example-template/copier.yaml'

tests/test_copier_schema.py:481: FileNotFoundError
=========================== short test summary info ============================
FAILED tests/test_copier_schema.py::TestExampleTemplateModuleIntegration::test_example_template_copier_yaml_exists
FAILED tests/test_copier_schema.py::TestExampleTemplateModuleIntegration::test_example_template_copier_yaml_is_parseable_yaml
FAILED tests/test_copier_schema.py::TestExampleTemplateModuleIntegration::test_example_template_copier_yaml_passes_schema_validation
FAILED tests/test_copier_schema.py::TestExampleTemplateModuleIntegration::test_example_template_name_follows_snake_case
FAILED tests/test_copier_schema.py::TestExampleTemplateModuleIntegration::test_example_template_version_follows_calver
================= 5 failed, 136 passed, 1 deselected in 0.36s ==================
```
