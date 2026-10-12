"""Tests for the gw-native gitweave-apply.yaml workflow."""
import pathlib, yaml

ROOT = pathlib.Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "gitweave-apply.yaml"


def test_workflow_is_valid_yaml():
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(doc, dict)


def test_plan_job_uses_fixture_mode():
    doc = yaml.safe_load(WORKFLOW.read_text())
    jobs = doc.get("jobs", {})
    plan_steps = []
    for job in jobs.values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            if "gw plan" in run and "--fixture" in run:
                plan_steps.append(step)
    assert plan_steps, "No step found running 'gw plan --fixture'"


def test_apply_job_uses_gw_apply():
    doc = yaml.safe_load(WORKFLOW.read_text())
    jobs = doc.get("jobs", {})
    apply_steps = []
    for job in jobs.values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            if run.strip() == "gw apply":
                apply_steps.append(step)
    assert apply_steps, "No step found running 'gw apply'"


def test_private_key_written_to_temp_file_not_echoed():
    content = WORKFLOW.read_text()
    assert "mktemp" in content, "Private key handling must use mktemp"
    assert "echo $GW_APP_PRIVATE_KEY\n" not in content
    assert 'echo "$GW_APP_PRIVATE_KEY"\n' not in content


def test_gw_resource_prefix_is_not_a_secret():
    """AC1: GW_RESOURCE_PREFIX must not come from secrets context — it is not sensitive."""
    content = WORKFLOW.read_text()
    assert "secrets.GW_RESOURCE_PREFIX" not in content, (
        "GW_RESOURCE_PREFIX must not be a secret — use vars.GW_RESOURCE_PREFIX "
        "or a plain workflow value instead"
    )
