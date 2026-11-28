#!/usr/bin/env bash
# Open Door's smoke checks, run by deploy.sh once the service has settled, and by hand at go-live.
#
# Every request goes to the load balancer at ALB_DNS_NAME while naming the real host, through
# `curl --connect-to`, so the checks work before the DNS record exists and after. Each check retries
# until it passes or its own deadline passes (measured with bash's SECONDS), SMOKE_DELAY_SECONDS apart
# (5, and never less than 1), and always makes at least one request. The first check (`/`) has SMOKE_FIRST_SECONDS (180),
# because services-stable can answer as soon as the task is running, before the load balancer counts
# the new target healthy (its checks run every 15 seconds and need 2 passes, after the target
# registers), and the load balancer answers 503 at once until then, so a count of tries would run out
# in under a minute. Each later check has SMOKE_SECONDS (30) of its own, so one transient error after
# the target is healthy does not fail a healthy deploy. Each request gives up after 10 seconds, so the
# worst case is about 181 + 10 + 2 x (31 + 10) = 273 seconds, under 5 minutes (a window, the extra second
# SECONDS needs, and a last request). A check that runs out of time exits 1 at once, naming it, without
# running the checks after it.
#
# Each app repository supplies its own smoke.sh, with its own host and checks: deploy.sh only calls
# $script_dir/smoke.sh, and knows nothing of this file's host.
set -euo pipefail

: "${ALB_DNS_NAME:?ALB_DNS_NAME is required}"
host=opendoor.jameslittlefield.net
first_seconds="${SMOKE_FIRST_SECONDS:-180}"
later_seconds="${SMOKE_SECONDS:-30}"
delay="${SMOKE_DELAY_SECONDS:-5}"

# Each setting must be a whole number of seconds (the two windows 0 or more, the delay 1 or more, so the
# loop can never hit the shared load balancer with no pause); anything else is a mistake to name, not to
# guess at.
for setting in SMOKE_FIRST_SECONDS:"$first_seconds" SMOKE_SECONDS:"$later_seconds" SMOKE_DELAY_SECONDS:"$delay"; do
  if [[ ! "${setting#*:}" =~ ^[0-9]+$ ]]; then
    echo "smoke.sh: ${setting%%:*} must be a non-negative whole number, got '${setting#*:}'" >&2
    exit 2
  fi
done
if ((10#$delay < 1)); then
  echo "smoke.sh: SMOKE_DELAY_SECONDS must be at least 1, got '$delay'" >&2
  exit 2
fi
first_seconds=$((10#$first_seconds))
later_seconds=$((10#$later_seconds))
delay=$((10#$delay))

# The body, then the status code on a line of its own. The address goes last.
fetch() {
  curl -sS --max-time 10 --connect-to "$host:443:$ALB_DNS_NAME:443" \
    -w '\n%{http_code}' "https://$host$1"
}

# The things a body is checked for, read from stdin. The readiness check needs only the 200.
anything() { cat >/dev/null; }
the_web_app() { grep -qF '<div id="root">'; }
the_availability() { jq -e 'type == "object" and has("available")' >/dev/null; }

# check <seconds> <path> <body check>: 200, and a body that passes, retried until it does or <seconds>
# have gone by since this check began. The first request is always made. SECONDS counts whole seconds,
# so the extra second keeps a check from stopping up to a second before its stated time.
check() {
  local seconds="$1" path="$2" body_check="$3" response remaining deadline=$((SECONDS + $1 + 1))
  while true; do
    if response="$(fetch "$path")" &&
      [[ "${response##*$'\n'}" == 200 ]] &&
      "$body_check" <<<"${response%$'\n'*}" 2>/dev/null; then
      echo "PASS: GET $path"
      return 0
    fi
    # Sleep the delay, or only what is left of the window if that is less, so a check retries for all
    # of its stated time and no longer.
    remaining=$((deadline - SECONDS))
    if ((remaining <= 0)); then break; fi
    sleep "$((delay < remaining ? delay : remaining))"
  done
  echo "FAIL: GET $path did not answer 200 with the expected body within $seconds seconds" >&2
  return 1
}

# `set -e` ends the script at the first check that fails (existing behavior, guarded by a test).
check "$first_seconds" / the_web_app
check "$later_seconds" /api/v1/health anything
check "$later_seconds" /api/v1/assistant/availability the_availability
