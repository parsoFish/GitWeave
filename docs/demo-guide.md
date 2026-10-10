# GitWeave End-to-End Demo Guide

A step-by-step walkthrough of the GitWeave subsystems. A second developer
following this guide from a **fresh clone** will be able to exercise bootstrap,
overlay config validation, apply-overlays dry-run, and Terraform plan — and see
passing results for each.

---

## Prerequisites

Install the following tools before starting:

| Tool | Minimum version | Install |
|------|-----------------|---------|
| `git` | 2.x | <https://git-scm.com/> |
| `terraform` | 1.5+ | <https://developer.hashicorp.com/terraform/install> |
| `python3` | 3.11+ | <https://www.python.org/downloads/> |
| `pip` | bundled with python3 | — |
| `curl` | any | usually pre-installed |

Verify each tool is on your PATH:

```bash
git --version && terraform --version && python3 --version && curl --version
```

---

## 1. Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/GitWeave.git
cd GitWeave
```

> All subsequent commands are run from the repository root unless a section
> explicitly says to change directory.

---

## 2. Bootstrap

The bootstrap script checks that every required tool and directory is present
before you attempt anything else.

```bash
bash scripts/bootstrap.sh
```

**Expected output:**

```text
🚀 Starting GitWeave Bootstrap...
Checking prerequisites...
✅ git found
✅ terraform found
✅ python3 found
Verifying directory structure...
✅ modules exists
✅ config exists
✅ infra exists
✅ .github/workflows exists
🎉 Bootstrap check complete! You can now proceed to 'infra/' to initialize Terraform.
```

If any prerequisite is missing, the script prints a `❌` message and exits
non-zero. Install the missing tool and re-run.

---

## 3. Overlay Config Validation (Dry-Run)

GitWeave validates repository overlay configurations against
`schemas/overlay.schema.json` before applying them. Run the test suite to
perform a dry-run validation of every YAML file under `config/`:

```bash
pip install -r requirements.txt --quiet
pytest tests/test_overlay_schema.py -v
```

**Expected output (all tests pass):**

```text
========================= test session starts ==========================
platform linux -- Python 3.11.x
collected N items

tests/test_overlay_schema.py::TestOverlaySchemaExists::test_schema_file_exists PASSED
tests/test_overlay_schema.py::...                                        PASSED
...

========================== N passed in 0.XXs ===========================
```

A `PASSED` line for every collected test indicates that:

- `schemas/overlay.schema.json` is valid JSON Schema
- `config/example.yaml` conforms to the schema (no errors, valid)

---

## 4. Apply Overlays Dry-Run

The overlay application step reads `config/` YAML files and would push
template changes to target repositories. In dry-run mode we validate the full
set of configs without making any remote changes:

```bash
pytest tests/ -v -k "overlay" --tb=short
```

**Expected output:**

```text
========================= test session starts ==========================
collected N items / M deselected

tests/test_overlay_schema.py::...         PASSED
tests/test_brownfield_import_validate.py::... PASSED
...

========================== N passed in X.XXs ===========================
```

`success` — all overlay-related tests pass, confirming that every config file
in `config/` is structurally valid and ready to apply.

---

## 5. Terraform Plan

The `infra/` directory contains the Terraform modules that provision GitHub
organisation resources (teams, branch-protection rules, etc.).

```bash
cd infra
terraform init
terraform plan
```

**Expected output:**

```text
Initializing the backend...
Initializing provider plugins...
...
Terraform has been successfully initialized!

...

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
```

> **Note:** If you are running against a real GitHub organisation, Terraform
> will show the planned additions/changes instead of "No changes". That is
> expected — the important signal is that `terraform plan` exits 0 and
> describes the intended changes without errors.

Return to the repo root when done:

```bash
cd ..
```

---

## Summary

| Step | Command | Pass indicator |
|------|---------|----------------|
| Bootstrap | `bash scripts/bootstrap.sh` | `Bootstrap check complete` |
| Overlay validation | `pytest tests/test_overlay_schema.py -v` | All tests `PASSED` |
| Apply overlays dry-run | `pytest tests/ -k "overlay"` | All tests `PASSED` |
| Terraform plan | `terraform init && terraform plan` (in `infra/`) | Exit 0, no errors |

All four steps passing confirms that GitWeave's subsystems are correctly
wired together on a fresh clone.
