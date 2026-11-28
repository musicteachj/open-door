"""The deploy files (`deploy/`), read as files, and `deploy/deploy.sh` run for real against a fake
`aws` and a fake `curl` (`tests/fixtures/deploy/bin`), which record every call and answer with
canned JSON. Nothing here reaches the network, Docker, or AWS.

Open Door has a setup task and a scheduled job (the cleanup), so the real `deploy/ecs` folder
exercises every path of the script. The one test that needs a changed folder copies it first.
"""

import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import Settings
from app.core.owner_settings import CleanupSettings, OwnerSettings

REPO = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO / "deploy"
ECS_DIR = DEPLOY_DIR / "ecs"
FAKE_BIN = Path(__file__).resolve().parent / "fixtures" / "deploy" / "bin"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

ACCOUNT = "123456789012"
IMAGE = f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/portfolio/opendoor:0123abc"
TARGET_GROUP_ARN = f"arn:aws:elasticloadbalancing:us-east-1:{ACCOUNT}:targetgroup/opendoor/abc"
ALB_DNS_NAME = "portfolio-alb.example"
HOST = "opendoor.jameslittlefield.net"
ARN_PREFIX = f"arn:aws:ecs:us-east-1:{ACCOUNT}"
SSM_PREFIX = "arn:aws:ssm:__REGION__:__ACCOUNT_ID__:parameter/portfolio/opendoor/"


def revision_arn(family: str) -> str:
    """What the fake answers register-task-definition with, for the family it was given."""
    return f"{ARN_PREFIX}:task-definition/{family}:7"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def task_definitions() -> dict[str, dict[str, Any]]:
    """Every task definition Open Door deploys, by file name: each file in deploy/ecs but the
    service."""
    files = sorted(f for f in ECS_DIR.glob("*.json") if f.name != "service.json")
    assert {f.name for f in files} == {"web.json", "setup.json", "cleanup.json"}
    return {f.stem: read_json(f) for f in files}


def container_of(name: str) -> dict[str, Any]:
    container: dict[str, Any] = task_definitions()[name]["containerDefinitions"][0]
    return container


def containers() -> list[dict[str, Any]]:
    return [d["containerDefinitions"][0] for d in task_definitions().values()]


def names(entries: list[dict[str, str]] | None) -> list[str]:
    return [entry["name"] for entry in entries or []]


def code_of(path: Path) -> str:
    """A script with its comment lines taken out, so a comment that names a flag is not the flag."""
    lines = path.read_text(encoding="utf-8").split("\n")
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


@dataclass
class Run:
    status: int
    output: str
    # One line per command the fakes saw, `aws ...` or `curl ...`, in order.
    calls: list[str]
    # Where the fake `aws` copied each `--cli-input-json` file, by its name.
    inputs: Path


def run(command: list[str], ecs_dir: Path, tmp: Path, fake: dict[str, str] | None = None) -> Run:
    # A folder of its own for each run, so a test that deploys twice keeps two call records.
    work = Path(tempfile.mkdtemp(dir=tmp))
    calls = work / "calls.log"
    inputs = work / "inputs"
    calls.write_text("")
    inputs.mkdir()
    # Built from nothing rather than from os.environ, so no AWS profile or key on this machine
    # would be in reach even if the fake were somehow not first on PATH.
    env = {
        "PATH": f"{FAKE_BIN}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(work),
        "AWS_CONFIG_FILE": "/dev/null",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_ACCOUNT_ID": ACCOUNT,
        "AWS_REGION": "us-east-1",
        "ALB_DNS_NAME": ALB_DNS_NAME,
        "TARGET_GROUP_ARN": TARGET_GROUP_ARN,
        "DEPLOY_ECS_DIR": str(ecs_dir),
        # Short deadlines, so a failing check ends the run in a second, not in minutes.
        "SMOKE_DELAY_SECONDS": "1",
        "SMOKE_FIRST_SECONDS": "1",
        "SMOKE_SECONDS": "1",
        "FAKE_CALLS": str(calls),
        "FAKE_INPUTS": str(inputs),
        **(fake or {}),
    }
    result = subprocess.run(  # noqa: S603
        ["bash", *command],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    return Run(
        status=result.returncode,
        output=result.stdout + result.stderr,
        calls=[line for line in calls.read_text(encoding="utf-8").split("\n") if line],
        inputs=inputs,
    )


def deploy(tmp_path: Path, fake: dict[str, str] | None = None, ecs_dir: Path = ECS_DIR) -> Run:
    return run([str(DEPLOY_DIR / "deploy.sh"), IMAGE], ecs_dir, tmp_path, fake)


def smoke(tmp_path: Path, fake: dict[str, str] | None = None) -> Run:
    return run([str(DEPLOY_DIR / "smoke.sh")], ECS_DIR, tmp_path, fake)


def service_calls(calls: list[str]) -> list[str]:
    return [call for call in calls if re.match(r"^aws ecs (create|update)-service", call)]


def run_setup_call() -> str:
    """The run-task call that starts the setup, as the fake records it."""
    return (
        "aws ecs run-task --cluster portfolio --launch-type EC2 "
        f"--task-definition {revision_arn('opendoor-setup')} --output json"
    )


def starting(calls: list[str], prefix: str) -> list[str]:
    return [call for call in calls if call.startswith(prefix)]


# --- the task definitions ---------------------------------------------------------------------


def test_the_image_sets_app_env_so_no_task_definition_does() -> None:
    # A blank or wrong APP_ENV would override the image's `production`. PORT and HOST are never
    # set in the deploy either (docs/DEPLOY.md).
    for container in containers():
        assert not {"APP_ENV", "PORT", "HOST"} & set(names(container.get("environment")))


def test_it_trusts_exactly_the_load_balancers_network() -> None:
    web = {e["name"]: e["value"] for e in container_of("web")["environment"]}
    assert web["FORWARDED_ALLOW_IPS"] == "10.20.0.0/16"
    assert web["AI_TRANSPORT"] == "anthropic"
    assert web["APP_ORIGIN"] == f"https://{HOST}"


def test_the_monthly_budget_is_a_parameter_not_a_plain_value() -> None:
    web = container_of("web")
    assert "AI_MONTHLY_BUDGET_USD" in names(web["secrets"])
    assert "AI_MONTHLY_BUDGET_USD" not in names(web["environment"])


def test_it_keeps_every_secret_in_ssm() -> None:
    # Addresses, not credentials, though their names say URL.
    not_secrets = {"APP_ORIGIN", "CLIENT_URL", "CORS_ORIGINS"}
    for container in containers():
        for name in names(container.get("environment")):
            if name not in not_secrets:
                assert not re.search(r"KEY|SECRET|PASSWORD|TOKEN|URI|URL", name), name
        for secret in container.get("secrets", []):
            assert secret["valueFrom"] == f"{SSM_PREFIX}{secret['name']}"


def test_it_names_only_settings_the_code_reads() -> None:
    read = {
        name.upper()
        for model in (Settings, OwnerSettings, CleanupSettings)
        for name in model.model_fields
    }
    for container in containers():
        used = names(container.get("environment")) + names(container.get("secrets"))
        assert used
        for name in used:
            assert name in read, name


def test_it_is_hardened() -> None:
    for container in containers():
        assert container["readonlyRootFilesystem"] is True
        tmpfs = container["linuxParameters"]["tmpfs"]
        assert "/tmp" in [mount["containerPath"] for mount in tmpfs]  # noqa: S108
        assert container["linuxParameters"]["capabilities"]["drop"] == ["ALL"]
        assert "no-new-privileges" in container["dockerSecurityOptions"]
        assert container.get("privileged", False) is False
        assert container["user"] == "10001:10001"


def test_it_tags_nothing() -> None:
    # The deploy role has no ecs:TagResource, so a tag on any of these would be refused.
    for path in ECS_DIR.glob("*.json"):
        document = read_json(path)
        for key in ("tags", "propagateTags", "enableECSManagedTags"):
            assert key not in document, f"{path.name} names {key}"


def test_the_web_container_matches_the_contract() -> None:
    web = container_of("web")
    assert web["name"] == "opendoor"
    assert web["portMappings"] == [{"containerPort": 8000, "hostPort": 0, "protocol": "tcp"}]
    assert (web["memoryReservation"], web["memory"], web["stopTimeout"]) == (256, 512, 30)
    assert "entryPoint" not in web
    health = web["healthCheck"]
    assert {k: health[k] for k in ("interval", "timeout", "retries", "startPeriod")} == {
        "interval": 15,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 20,
    }
    assert "/api/v1/health/live" in health["command"][-1]
    assert read_json(ECS_DIR / "service.json")["loadBalancers"][0]["containerName"] == "opendoor"


def test_it_runs_the_setup_with_its_own_entry_point() -> None:
    setup = task_definitions()["setup"]
    assert setup["family"] == "opendoor-setup"
    assert setup["containerDefinitions"][0]["entryPoint"] == ["/app/setup.sh"]
    assert setup["containerDefinitions"][0]["memory"] == 256
    cleanup = task_definitions()["cleanup"]
    assert cleanup["family"] == "opendoor-cleanup"
    assert cleanup["containerDefinitions"][0]["entryPoint"] == ["/app/cleanup.sh"]
    assert cleanup["containerDefinitions"][0]["memory"] == 128
    # No job serves, so none opens a port or runs a health check.
    for job in (setup, cleanup):
        assert "portMappings" not in job["containerDefinitions"][0]
        assert "healthCheck" not in job["containerDefinitions"][0]


def test_it_gives_the_setup_the_three_urls_and_no_keyring_or_model_key() -> None:
    setup = container_of("setup")
    assert names(setup["secrets"]) == [
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "CLEANUP_DATABASE_URL",
    ]
    # Production validates the origin whenever Settings loads, which the setup's scripts do.
    assert names(setup["environment"]) == ["APP_ORIGIN"]


def test_it_gives_the_cleanup_only_its_database_url() -> None:
    cleanup = container_of("cleanup")
    assert names(cleanup["secrets"]) == ["CLEANUP_DATABASE_URL"]
    assert names(cleanup.get("environment")) == []


# --- deploy.sh --------------------------------------------------------------------------------


@pytest.mark.parametrize("script", ["deploy.sh", "smoke.sh", "head-of-main.sh"])
def test_it_never_traces_the_script(script: str) -> None:
    code = code_of(DEPLOY_DIR / script)
    assert "set -euo pipefail" in code
    assert not re.search(r"set -[a-z]*x", code)
    assert "set -o xtrace" not in code
    assert "envsubst" not in code


def test_it_registers_every_task_definition_with_every_placeholder_filled(tmp_path: Path) -> None:
    result = deploy(tmp_path)
    assert result.status == 0, result.output
    for name in ("web", "setup", "cleanup", "create-service"):
        registered = (result.inputs / f"{name}.json").read_text(encoding="utf-8")
        assert not re.search(r"__[A-Z][A-Z_]*__", registered), name
    web = read_json(result.inputs / "web.json")
    assert web["containerDefinitions"][0]["image"] == IMAGE
    assert web["executionRoleArn"] == f"arn:aws:iam::{ACCOUNT}:role/opendoor-execution"
    secret = web["containerDefinitions"][0]["secrets"][0]["valueFrom"]
    assert secret.startswith(f"arn:aws:ssm:us-east-1:{ACCOUNT}:parameter/portfolio/opendoor/")


def test_it_runs_the_setup_to_completion_before_the_service(tmp_path: Path) -> None:
    result = deploy(tmp_path)
    assert result.status == 0, result.output
    ran = result.calls.index(run_setup_call())
    service = next(i for i, c in enumerate(result.calls) if re.match(r"aws ecs create-service", c))
    assert ran < service


def test_it_stops_before_the_service_when_setup_fails(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SETUP": "failed"})
    assert result.status == 1
    assert service_calls(result.calls) == []
    assert run_setup_call() in result.calls
    # The log is read by the stream name ECS gives it: <prefix>/<container>/<task id>.
    assert (
        "aws logs get-log-events --log-group-name /portfolio/opendoor "
        "--log-stream-name setup/opendoor-setup/setuptask1 --limit 50 --output json"
    ) in result.calls
    assert "migration 7 failed" in result.output
    assert starting(result.calls, "aws ssm") == []


@pytest.mark.parametrize("setup", ["no-exit-code", "unplaced"])
def test_it_stops_before_the_service_when_the_setup_task_does_not_finish_cleanly(
    tmp_path: Path, setup: str
) -> None:
    # A container with no exit code, and a task that was never placed.
    result = deploy(tmp_path, {"FAKE_SETUP": setup})
    assert result.status == 1
    assert service_calls(result.calls) == []


@pytest.mark.parametrize("service", ["zero", "draining"])
def test_it_runs_no_setup_for_a_service_that_would_refuse_the_deploy(
    tmp_path: Path, service: str
) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": service})
    assert result.status == 1
    assert starting(result.calls, "aws ecs run-task") == []
    assert service_calls(result.calls) == []


def test_it_names_the_setup_task_when_it_does_not_stop_in_time(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SETUP": "timeout"})
    assert result.status == 1
    assert f"{ARN_PREFIX}:task/portfolio/setuptask1" in result.output
    assert "may still be running" in result.output
    assert "do not re-run" in result.output
    assert "aws ecs describe-tasks --cluster portfolio --tasks" in result.output
    assert service_calls(result.calls) == []
    assert starting(result.calls, "aws ecs stop-task") == []


@pytest.mark.parametrize(
    ("setup", "succeeds"),
    [
        ("timeout-stopped", True),
        ("timeout-stopped-failed", False),
        # Still STOPPING, but every container has already exited 0.
        ("timeout-stopping", True),
    ],
)
def test_it_judges_a_setup_that_stopped_just_after_the_waiter_gave_up_by_its_exit_code(
    tmp_path: Path, setup: str, succeeds: bool
) -> None:
    result = deploy(tmp_path, {"FAKE_SETUP": setup})
    assert (result.status == 0) is succeeds, result.output
    assert len(service_calls(result.calls)) == (1 if succeeds else 0)
    if not succeeds:
        assert "the setup task failed" in result.output


@pytest.mark.parametrize("stop_code", ["UserInitiated", "ServiceSchedulerInitiated"])
def test_it_fails_a_setup_that_ecs_stopped_even_when_its_exit_code_is_0(
    tmp_path: Path, stop_code: str
) -> None:
    # A migration that trapped SIGTERM and exited 0 half done must not pass as a finished setup.
    result = deploy(tmp_path, {"FAKE_STOP_CODE": stop_code})
    assert result.status == 1
    assert f"stop code {stop_code}" in result.output
    assert "was stopped by ECS" in result.output
    assert service_calls(result.calls) == []
    assert starting(result.calls, "aws ssm") == []


def test_it_does_not_trust_a_setup_with_exit_code_0_and_no_stop_code(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_STOP_CODE": "absent"})
    assert result.status == 1
    assert "exited 0, but ECS reported no stop code" in result.output
    assert "was stopped by ECS" not in result.output
    assert service_calls(result.calls) == []


def test_it_names_the_stop_code_only_when_every_container_exited_0(tmp_path: Path) -> None:
    # A failed container stopped by ECS is a plain failure: the exit code is the news.
    result = deploy(tmp_path, {"FAKE_SETUP": "failed", "FAKE_STOP_CODE": "UserInitiated"})
    assert result.status == 1
    assert "the setup task failed, so the service was not touched" in result.output
    assert "was stopped by ECS" not in result.output
    assert service_calls(result.calls) == []


def test_it_says_what_to_check_when_the_setup_task_failed_to_start(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SETUP": "no-exit-code", "FAKE_STOP_CODE": "TaskFailedToStart"})
    assert result.status == 1
    assert "failed to start (stop code TaskFailedToStart)" in result.output
    assert "image pull" in result.output
    assert "free memory" in result.output
    assert service_calls(result.calls) == []


def test_it_does_not_settle_a_stopping_task_that_has_no_stop_code_yet(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SETUP": "timeout-stopping-no-stop-code"})
    assert result.status == 1
    assert "may still be running" in result.output
    assert service_calls(result.calls) == []


def test_it_passes_a_setup_whose_essential_container_exited_by_itself(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_STOP_CODE": "EssentialContainerExited"})
    assert result.status == 0, result.output
    assert len(service_calls(result.calls)) == 1


def test_it_creates_the_service_the_first_time_and_updates_it_after(tmp_path: Path) -> None:
    web_arn = revision_arn("opendoor-web")

    first = deploy(tmp_path)
    assert first.status == 0, first.output
    created = service_calls(first.calls)
    assert len(created) == 1
    assert re.match(r"^aws ecs create-service --cli-input-json file://", created[0])
    # The full revision ARN: the deploy role's condition refuses a bare family.
    service = read_json(first.inputs / "create-service.json")
    assert service["taskDefinition"] == web_arn
    assert service["loadBalancers"][0]["targetGroupArn"] == TARGET_GROUP_ARN

    second = deploy(tmp_path, {"FAKE_SERVICE": "active"})
    assert second.status == 0, second.output
    updated = service_calls(second.calls)
    assert len(updated) == 1
    assert updated[0].startswith(
        "aws ecs update-service --cluster portfolio --service opendoor --task-definition "
    )
    assert f"--task-definition {web_arn} " in updated[0]


def test_it_carries_the_deployment_settings_into_an_update_and_never_the_desired_count(
    tmp_path: Path,
) -> None:
    service = read_json(ECS_DIR / "service.json")
    result = deploy(tmp_path, {"FAKE_SERVICE": "active"})
    assert result.status == 0, result.output
    (update,) = service_calls(result.calls)
    # jq -c and json.dumps with these separators both write compact JSON in the file's key order.
    settings = json.dumps(service["deploymentConfiguration"], separators=(",", ":"))
    assert f"--deployment-configuration {settings} " in update
    grace = service["healthCheckGracePeriodSeconds"]
    assert f"--health-check-grace-period-seconds {grace} " in update
    assert "--desired-count" not in update
    # The target group comes from service.json, so a replaced group takes effect on the next deploy.
    balancers = [{**b, "targetGroupArn": TARGET_GROUP_ARN} for b in service["loadBalancers"]]
    assert f"--load-balancers {json.dumps(balancers, separators=(',', ':'))}" in update


def test_it_refuses_a_service_that_is_still_draining(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "draining"})
    assert result.status == 1
    assert service_calls(result.calls) == []
    assert "service is still draining; wait until it is INACTIVE and re-run" in result.output


def test_it_refuses_a_service_that_was_scaled_to_0_on_purpose(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "zero"})
    assert result.status == 1
    assert service_calls(result.calls) == []
    assert "scaled to 0 on purpose" in result.output
    assert (
        "aws ecs update-service --cluster portfolio --service opendoor --desired-count 1"
        in result.output
    )


@pytest.mark.parametrize(
    "key", ["deploymentConfiguration", "healthCheckGracePeriodSeconds", "loadBalancers"]
)
def test_it_fails_when_service_json_lacks_a_key_an_update_needs(tmp_path: Path, key: str) -> None:
    copy = tmp_path / "ecs"
    shutil.copytree(ECS_DIR, copy)
    service = read_json(copy / "service.json")
    del service[key]
    (copy / "service.json").write_text(json.dumps(service), encoding="utf-8")
    result = deploy(tmp_path, {"FAKE_SERVICE": "active"}, ecs_dir=copy)
    assert result.status == 1
    assert service_calls(result.calls) == []
    assert f"service.json needs {key}" in result.output


def test_it_waits_again_when_the_waiter_times_out(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "active", "FAKE_WAIT_TIMEOUTS": "1"})
    assert result.status == 0, result.output
    assert len(starting(result.calls, "aws ecs wait services-stable")) == 2


def test_it_gives_up_after_three_waits_that_time_out(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "active", "FAKE_WAIT_TIMEOUTS": "3"})
    assert result.status == 1
    assert len(starting(result.calls, "aws ecs wait services-stable")) == 3
    assert starting(result.calls, "curl") == []


def test_it_does_not_wait_again_when_the_waiter_fails_for_another_reason(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "active", "FAKE_WAIT_TERMINAL": "1"})
    assert result.status == 1
    assert len(starting(result.calls, "aws ecs wait services-stable")) == 1
    assert starting(result.calls, "curl") == []


def test_it_creates_the_service_again_when_it_is_inactive(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "inactive"})
    assert result.status == 0, result.output
    created = service_calls(result.calls)
    assert len(created) == 1
    assert created[0].startswith("aws ecs create-service --cli-input-json file://")


def test_it_fails_when_the_circuit_breaker_rolled_the_service_back(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_SERVICE": "active", "FAKE_ROLLBACK": "1"})
    assert result.status == 1
    assert "rolled" in result.output
    assert starting(result.calls, "curl") == []


def test_it_writes_the_cleanup_revision_only_after_smoke_passes(tmp_path: Path) -> None:
    result = deploy(tmp_path)
    assert result.status == 0, result.output
    puts = [i for i, c in enumerate(result.calls) if c.startswith("aws ssm put-parameter")]
    assert len(puts) == 1
    assert result.calls[puts[0]] == (
        "aws ssm put-parameter --name /portfolio/opendoor/cleanup-revision --type String "
        "--value 7 --overwrite --output json"
    )
    smoke_calls = [i for i, c in enumerate(result.calls) if c.startswith("curl")]
    assert smoke_calls
    assert puts[0] > smoke_calls[-1]


def test_it_writes_no_job_revision_when_smoke_fails(tmp_path: Path) -> None:
    result = deploy(tmp_path, {"FAKE_CURL_STATUS": "503"})
    assert result.status == 1
    assert len(service_calls(result.calls)) == 1
    assert starting(result.calls, "aws ssm") == []


# --- the deploy job ---------------------------------------------------------------------------


def deploy_steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][
        "deploy"
    ]["steps"]
    return steps


def test_the_deploy_job_builds_and_pushes_one_plain_image_per_tag() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    builds = [line for line in workflow.split("\n") if "docker buildx build" in line]
    assert len(builds) == 1
    assert "--provenance=false" in builds[0]
    assert "--sbom=false" in builds[0]
    assert "--push" in builds[0]
    assert "--load" not in builds[0]
    assert "docker push" not in workflow
    assert "${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}" in workflow


def test_the_deploy_job_waits_for_every_other_job() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert set(jobs["deploy"]["needs"]) == set(jobs) - {"deploy"}
    assert jobs["deploy"]["timeout-minutes"] == 58
    assert jobs["deploy"]["environment"] == "production"
    # A skipped (path-filtered) job must not skip the deploy, which the implicit success() would.
    condition = jobs["deploy"]["if"]
    # GitHub's own British spelling is the result name, so it is spelled out in two pieces here.
    canceled = "cancel" + "led"
    assert f"!{canceled}()" in condition
    assert "!contains(needs.*.result, 'failure')" in condition
    assert f"!contains(needs.*.result, '{canceled}')" in condition


def test_the_build_and_push_step_has_its_own_8_minute_limit() -> None:
    steps = deploy_steps()
    build = next(step for step in steps if step.get("name") == "Build and push the image")
    assert build["timeout-minutes"] == 8


def test_the_deploy_job_checks_the_head_of_main_before_credentials_and_before_the_push() -> None:
    steps = deploy_steps()
    names_in_order = [step.get("name", "") for step in steps]
    first = names_in_order.index("Refuse a run that is not for the head of main")
    credentials = names_in_order.index("Configure AWS credentials")
    ecr = names_in_order.index("Log in to ECR")
    second = names_in_order.index("Refuse again, right before the push, if main moved")
    build = names_in_order.index("Build and push the image")
    deploy_step = names_in_order.index("Deploy")
    # The order: first check, credentials, ECR login, second check, build and push, deploy.
    assert first < credentials < ecr < second < build < deploy_step
    # Nothing sits between the second check and the push.
    assert build == second + 1
    for guard in (steps[first], steps[second]):
        # The script reads its inputs from env, and the step's script text holds no expression.
        assert guard["env"] == {
            "GH_TOKEN": "${{ github.token }}",
            "RUN_SHA": "${{ github.sha }}",
            "REPO": "${{ github.repository }}",
        }
        assert guard["run"] == "deploy/head-of-main.sh"


def test_only_pull_requests_cancel_a_running_workflow() -> None:
    # A run by hand shares the push run's group, and must not cancel a deploy under way.
    cancel = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["concurrency"][
        "cancel-in-progress"
    ]
    assert cancel is not True
    assert cancel == "${{ github.event_name == 'pull_request' }}"


# --- smoke.sh ---------------------------------------------------------------------------------


def test_smoke_asks_the_three_addresses_through_the_load_balancer_with_a_time_limit(
    tmp_path: Path,
) -> None:
    result = smoke(tmp_path)
    assert result.status == 0, result.output
    assert [call.split(" ")[-1] for call in result.calls] == [
        f"https://{HOST}/",
        f"https://{HOST}/api/v1/health",
        f"https://{HOST}/api/v1/assistant/availability",
    ]
    for call in result.calls:
        assert f"--connect-to {HOST}:443:{ALB_DNS_NAME}:443" in call
        assert re.search(r"--max-time \d+", call)


def test_smoke_fails_an_availability_reply_without_available(tmp_path: Path) -> None:
    result = smoke(tmp_path, {"FAKE_CURL_BODY": '<div id="root"></div>'})
    assert result.status == 1
    assert "FAIL: GET /api/v1/assistant/availability" in result.output


def test_smoke_defaults_are_180_seconds_for_the_first_check_and_30_for_each_later_one() -> None:
    code = code_of(DEPLOY_DIR / "smoke.sh")
    assert "SMOKE_FIRST_SECONDS:-180" in code
    assert "SMOKE_SECONDS:-30" in code


def test_smoke_stops_at_the_first_failed_check_and_asks_for_no_later_one(tmp_path: Path) -> None:
    result = smoke(tmp_path, {"FAKE_CURL_STATUS": "503", "SMOKE_FIRST_SECONDS": "0"})
    assert result.status == 1
    assert "FAIL: GET / did not answer 200" in result.output
    # The first check may make a couple of requests before its deadline; none is for a later check.
    assert {call.split(" ")[-1] for call in result.calls} == {f"https://{HOST}/"}


def test_smoke_keeps_retrying_the_first_check_until_it_passes_or_its_deadline_passes(
    tmp_path: Path,
) -> None:
    passes = smoke(tmp_path, {"FAKE_CURL_FAIL_FIRST": "2", "SMOKE_FIRST_SECONDS": "20"})
    assert passes.status == 0, passes.output
    assert len(passes.calls) == 5
    started = time.monotonic()
    fails = smoke(
        tmp_path,
        {"FAKE_CURL_STATUS": "503", "SMOKE_FIRST_SECONDS": "2", "SMOKE_DELAY_SECONDS": "1"},
    )
    assert fails.status == 1
    assert time.monotonic() - started >= 2
    assert len(fails.calls) >= 2


def test_smoke_gives_a_later_check_its_own_fresh_deadline_not_what_is_left_of_the_first(
    tmp_path: Path,
) -> None:
    # / (5 seconds) fails 4 times and passes on its fifth request, about 4 seconds in. The health
    # check (5 seconds) then fails 4 times and passes on its fifth, about 4 seconds after it began
    # and 8 in: inside its own window, but long past a window counted from the start of the run.
    result = smoke(
        tmp_path,
        {
            "FAKE_CURL_FAIL_ON": "1,2,3,4,6,7,8,9",
            "SMOKE_FIRST_SECONDS": "5",
            "SMOKE_SECONDS": "5",
            "SMOKE_DELAY_SECONDS": "1",
        },
    )
    assert result.status == 0, result.output
    assert len(result.calls) == 11


def test_smoke_fails_the_run_when_a_later_check_never_passes_and_never_asks_for_the_next(
    tmp_path: Path,
) -> None:
    result = smoke(
        tmp_path,
        {
            "FAKE_CURL_FAIL_ON": "2,3,4,5,6,7,8,9",
            "SMOKE_SECONDS": "1",
            "SMOKE_DELAY_SECONDS": "1",
        },
    )
    assert result.status == 1
    assert "FAIL: GET /api/v1/health" in result.output
    assert not any(call.endswith("/api/v1/assistant/availability") for call in result.calls)


def test_smoke_passes_with_one_request_each_when_all_three_checks_pass_early(
    tmp_path: Path,
) -> None:
    result = smoke(tmp_path)
    assert result.status == 0, result.output
    assert len(result.calls) == 3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SMOKE_FIRST_SECONDS", "abc"),
        ("SMOKE_SECONDS", "-1"),
        ("SMOKE_DELAY_SECONDS", "1.5"),
        ("SMOKE_DELAY_SECONDS", "0"),
    ],
)
def test_smoke_refuses_a_setting_that_is_not_a_whole_number_before_any_request(
    tmp_path: Path, name: str, value: str
) -> None:
    result = smoke(tmp_path, {name: value})
    assert result.status == 2
    assert name in result.output
    assert result.calls == []


# --- head-of-main.sh --------------------------------------------------------------------------


def head_of_main(tmp_path: Path, main: str) -> Run:
    return run(
        [str(DEPLOY_DIR / "head-of-main.sh")],
        ECS_DIR,
        tmp_path,
        {"RUN_SHA": "aaaa111", "REPO": "owner/repo", "GH_TOKEN": "token", "FAKE_MAIN_SHA": main},
    )


def test_head_of_main_passes_when_the_run_is_for_the_head_of_main(tmp_path: Path) -> None:
    result = head_of_main(tmp_path, "aaaa111")
    assert result.status == 0, result.output
    assert result.calls == ["gh api repos/owner/repo/branches/main --jq .commit.sha"]


def test_head_of_main_refuses_a_run_for_any_other_commit_naming_both(tmp_path: Path) -> None:
    result = head_of_main(tmp_path, "bbbb222")
    assert result.status == 1
    assert "This run is for aaaa111, but main is now bbbb222." in result.output
    assert "run the workflow by hand on main" in result.output
