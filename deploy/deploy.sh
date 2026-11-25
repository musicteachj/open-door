#!/usr/bin/env bash
# Deploys one image onto the shared portfolio cluster: deploy/deploy.sh <image>
#
# The deploy contract from portfolio-infra's Phase 3 plan, in its seven steps. It is generic on
# purpose, so the same file serves every app repository: the slug and the cluster come from
# service.json, and DEPLOY_ECS_DIR points it at another folder of ECS JSON (the tests use it to
# try a service.json with a key missing). Open Door has a setup task and a scheduled job.
#
#   ecs/web.json      the <slug>-web task definition, which the service runs
#   ecs/setup.json    optional: run once, to completion, before the service is touched
#   ecs/<job>.json    optional, any other name: a scheduled job, such as cleanup.json
#   ecs/service.json  the create-service input
#
# It stays inside the <slug>-deploy role: every service call names the full task-definition
# revision ARN (the role refuses a bare family), nothing is tagged, and a setup task's log is read
# by its stream name alone. It needs AWS_ACCOUNT_ID, TARGET_GROUP_ARN and ALB_DNS_NAME (smoke.sh
# reads the last), and AWS_REGION, us-east-1 unless set.
#
# No tracing, ever: the task definitions hold SSM parameter names rather than values, so there
# is nothing secret to print today, but a trace would print whatever a later edit adds.
set -euo pipefail

fail() {
  echo "deploy: $*" >&2
  exit 1
}

if [[ $# -ne 1 ]]; then
  echo "usage: deploy.sh <image>" >&2
  exit 2
fi
image="$1"
: "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"
: "${TARGET_GROUP_ARN:?TARGET_GROUP_ARN is required}"
: "${ALB_DNS_NAME:?ALB_DNS_NAME is required, for smoke.sh}"
region="${AWS_REGION:-us-east-1}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ecs_dir="${DEPLOY_ECS_DIR:-$script_dir/ecs}"
[[ -f "$ecs_dir/web.json" && -f "$ecs_dir/service.json" ]] ||
  fail "$ecs_dir needs web.json and service.json"

rendered="$(mktemp -d)"
trap 'rm -rf "$rendered"' EXIT

# 1. Render. jq replaces the four placeholders inside string values and touches nothing else, so
#    no other `$` or backtick in the JSON can expand the way it would in a shell substitution.
echo "==> Rendering $ecs_dir"
for file in "$ecs_dir"/*.json; do
  name="$(basename "$file")"
  jq --arg image "$image" --arg account "$AWS_ACCOUNT_ID" --arg region "$region" \
    --arg target_group "$TARGET_GROUP_ARN" '
    walk(if type == "string" then
      gsub("__IMAGE__"; $image) | gsub("__ACCOUNT_ID__"; $account)
      | gsub("__REGION__"; $region) | gsub("__TARGET_GROUP_ARN__"; $target_group)
    else . end)' "$file" >"$rendered/$name"
  if grep -q '__[A-Z][A-Z_]*__' "$rendered/$name"; then
    fail "$name holds a placeholder this script does not fill"
  fi
done

slug="$(jq -r '.serviceName // empty' "$rendered/service.json")"
cluster="$(jq -r '.cluster // empty' "$rendered/service.json")"
[[ -n "$slug" && -n "$cluster" ]] || fail "service.json needs serviceName and cluster"
# An update reads these three out of service.json, and jq prints a missing key as the word null.
for key in deploymentConfiguration healthCheckGracePeriodSeconds loadBalancers; do
  jq -e --arg key "$key" '.[$key] != null' "$rendered/service.json" >/dev/null ||
    fail "service.json needs $key, which an update passes to the service"
done

# 2. Register every task definition. Keep the web revision ARN for the service, and each
#    scheduled job's revision number for step 7, as "<job> <revision>" lines.
echo "==> Registering task definitions"
web_arn=""
setup_arn=""
jobs=""
for file in "$rendered"/*.json; do
  name="$(basename "$file" .json)"
  if [[ "$name" == service ]]; then continue; fi
  registered="$(aws ecs register-task-definition --cli-input-json "file://$file" --output json)"
  arn="$(jq -r '.taskDefinition.taskDefinitionArn // empty' <<<"$registered")"
  revision="$(jq -r '.taskDefinition.revision // empty' <<<"$registered")"
  [[ "$arn" == arn:* && -n "$revision" ]] || fail "registering $name.json returned no revision"
  echo "    $name: $arn"
  case "$name" in
    web) web_arn="$arn" ;;
    setup) setup_arn="$arn" ;;
    *) jobs="$jobs$name $revision"$'\n' ;;
  esac
done

# The last 50 lines of each setup container's log. The stream is named
# <awslogs-stream-prefix>/<container>/<task id>, which the role can read without listing streams.
print_setup_log() {
  local task_id="${1##*/}" container group prefix stream
  while IFS=$'\t' read -r container group prefix; do
    stream="$prefix/$container/$task_id"
    echo "==> The last 50 lines of $group $stream" >&2
    aws logs get-log-events --log-group-name "$group" --log-stream-name "$stream" \
      --limit 50 --output json </dev/null | jq -r '.events[].message' >&2 ||
      echo "    (the log stream could not be read)" >&2
  done < <(jq -r '.containerDefinitions[]
    | [.name, .logConfiguration.options["awslogs-group"], .logConfiguration.options["awslogs-stream-prefix"]]
    | @tsv' "$rendered/setup.json")
}

# Before step 3, look at the service once, and refuse before the setup task runs: a deploy that will
#    be refused must not have run a setup task (a migration) first, or the schema would be ahead of
#    the code. (Registering a revision above changes nothing that serves.)
#    The same reply decides, in step 4, between an update and a create.
echo "==> Checking $cluster/$slug"
described="$(aws ecs describe-services --cluster "$cluster" --services "$slug" --output json)"
status="$(jq -r '.services[0].status // empty' <<<"$described")"
if [[ "$status" == DRAINING ]]; then
  fail "service is still draining; wait until it is INACTIVE and re-run"
fi
if [[ "$status" == ACTIVE && "$(jq -r '.services[0].desiredCount' <<<"$described")" == 0 ]]; then
  fail "$slug is scaled to 0 on purpose, so the deploy would leave it with no tasks and smoke would fail;" \
    "scale it back to 1 (aws ecs update-service --cluster $cluster --service $slug --desired-count 1)" \
    "and re-run the deploy"
fi

# 3. Setup, before anything that serves traffic changes. Any container that does not stop with
#    exit code 0 (a failure, no exit code at all, or a task never placed), and any task ECS stopped for
#    a reason other than its essential container exiting, ends the deploy here, with the old version
#    still serving.
if [[ -n "$setup_arn" ]]; then
  echo "==> Running the setup task"
  started="$(aws ecs run-task --cluster "$cluster" --launch-type EC2 \
    --task-definition "$setup_arn" --output json)"
  task_arn="$(jq -r '.tasks[0].taskArn // empty' <<<"$started")"
  if [[ -z "$task_arn" ]]; then
    jq -r '.failures[]? | "    \(.reason // "no reason given") \(.detail // "")"' <<<"$started" >&2
    fail "the setup task was not placed, so the service was not touched"
  fi
  if ! aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"; then
    # The waiter gives up after about 10 minutes, and the task may be running still. The deploy
    # role cannot stop it, so say so: a re-run would start a second setup on the same database.
    settled="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" --output json |
      jq -r '(.tasks[0] // {}) as $t | ($t.containers // []) as $c
        | $t.lastStatus == "STOPPED"
        or (($c | length) > 0 and ($c | all(.exitCode != null)) and $t.stopCode != null)' || true)"
    # A task that stopped just after the waiter gave up (or that is still STOPPING with every
    # container exited and its stop code set) is judged by its exit code below, like any other stopped task: a clean setup
    # must not fail the deploy.
    if [[ "$settled" != true ]]; then
      fail "the setup task $task_arn did not stop in time and may still be running;" \
        "do not re-run the deploy until it has stopped" \
        "(aws ecs describe-tasks --cluster $cluster --tasks $task_arn shows STOPPED)," \
        "because a re-run would start a second setup against the same database;" \
        "the service was not touched"
    fi
  fi
  stopped="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" --output json)"
  # Exit code 0 is not enough: a task stopped with any stop code but EssentialContainerExited (a manual
  # stop is UserInitiated) can have a migration that trapped SIGTERM and exited 0 half done. Only a task
  # whose essential container exited by itself is a finished setup.
  stop_code="$(jq -r '.tasks[0].stopCode // "none"' <<<"$stopped")"
  all_exited_0=false
  if jq -e '[.tasks[0].containers[]? | .exitCode == 0] | length > 0 and all' \
    <<<"$stopped" >/dev/null; then
    all_exited_0=true
  fi
  if [[ "$all_exited_0" != true || "$stop_code" != EssentialContainerExited ]]; then
    jq -r '.tasks[0] | "    stopped: \(.stoppedReason // "no reason given") (stop code \(.stopCode // "none"))",
      (.containers[]? | "    \(.name): exit code \(.exitCode // "none") \(.reason // "")")' \
      <<<"$stopped" >&2
    print_setup_log "$task_arn"
    if [[ "$stop_code" == TaskFailedToStart ]]; then
      fail "the setup task failed to start (stop code TaskFailedToStart):" \
        "check the image pull and the instance's free memory; the service was not touched"
    fi
    # Every container exited 0, but ECS gave no stop code, so nothing says the task finished by itself.
    if [[ "$all_exited_0" == true && "$stop_code" == none ]]; then
      fail "the setup task exited 0, but ECS reported no stop code, so it can't be trusted;" \
        "check aws ecs describe-tasks --cluster $cluster --tasks $task_arn; the service was not touched"
    fi
    # Every container exited 0 but ECS, not the task, ended it: the trapped-signal case.
    if [[ "$all_exited_0" == true ]]; then
      fail "the setup task was stopped by ECS (stop code $stop_code), not by finishing, so the service was not touched"
    fi
    fail "the setup task failed, so the service was not touched"
  fi
  echo "    setup succeeded"
fi

# 4. Update the service if it is there, or create it from service.json. Both name the web
#    revision ARN. Their replies describe the service and are not printed.
echo "==> Deploying $web_arn to $cluster/$slug"
if [[ "$status" == ACTIVE ]]; then
  # The deployment settings, the grace period and the load balancers come from service.json on
  # every update, so an edit to them (a replaced target group, say) takes effect at the next
  # deploy rather than only when the service is created. The desired count does not: a deploy
  # must not undo a deliberate scale to 0 during an incident or the failover drill.
  aws ecs update-service --cluster "$cluster" --service "$slug" \
    --task-definition "$web_arn" \
    --deployment-configuration "$(jq -c '.deploymentConfiguration' "$rendered/service.json")" \
    --health-check-grace-period-seconds \
    "$(jq -r '.healthCheckGracePeriodSeconds' "$rendered/service.json")" \
    --load-balancers "$(jq -c '.loadBalancers' "$rendered/service.json")" \
    --output json >/dev/null
else
  jq --arg task_definition "$web_arn" '.taskDefinition = $task_definition' \
    "$rendered/service.json" >"$rendered/create-service.json"
  aws ecs create-service --cli-input-json "file://$rendered/create-service.json" \
    --output json >/dev/null
fi

# 5. Wait for it to settle, then check it settled on this release: once the circuit breaker
#    has rolled a failed deployment back, the service is stable again, on the old revision.
#    One services-stable wait gives up after 10 minutes (40 polls 15 seconds apart), so it is
#    asked up to 3 times, 30 minutes in all. With the build and push (8 minutes at most, their own cap),
#    a setup task's wait of up to 10 minutes, smoke (about 5 minutes at most) and a minute for checkout,
#    login and the guards, the worst case is about 54 minutes, inside the job's 58. Only its time limit is
#    retried: any other failure (the service missing, draining or inactive) ends the deploy at once.
echo "==> Waiting for $slug to settle"
for round in 1 2 3; do
  if waited="$(aws ecs wait services-stable --cluster "$cluster" --services "$slug" 2>&1)"; then
    break
  fi
  if [[ "$waited" != *"Max attempts exceeded"* ]]; then
    echo "$waited" >&2
    fail "$slug did not settle"
  fi
  if [[ "$round" == 3 ]]; then
    fail "$slug did not settle in 30 minutes; the circuit breaker rolls a failed deployment back"
  fi
  echo "    still settling after $((round * 10)) minutes"
done
serving="$(aws ecs describe-services --cluster "$cluster" --services "$slug" --output json |
  jq -r '.services[0].deployments[]? | select(.status == "PRIMARY") | .taskDefinition')"
[[ "$serving" == "$web_arn" ]] ||
  fail "$slug settled on ${serving:-nothing}, not $web_arn: the circuit breaker rolled it back"

# 6. Smoke, through the load balancer.
echo "==> Smoke checks"
"$script_dir/smoke.sh" ||
  fail "smoke checks failed with $web_arn serving; no job revision was written"

# 7. Only now, each job's revision, for the next infrastructure deploy to schedule.
while read -r job revision; do
  if [[ -z "$job" ]]; then continue; fi
  aws ssm put-parameter --name "/portfolio/$slug/$job-revision" --type String \
    --value "$revision" --overwrite --output json </dev/null >/dev/null
  echo "    /portfolio/$slug/$job-revision is $revision"
done <<<"$jobs"

echo "==> Deployed $web_arn"
