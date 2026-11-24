#!/usr/bin/env bash
# Open Door's smoke checks, run by deploy.sh once the service has settled, and by hand at go-live.
#
# Every request goes to the load balancer at ALB_DNS_NAME while naming the real host, through
# `curl --connect-to`, so the checks work before the DNS record exists and after. Each check
# tries up to SMOKE_ATTEMPTS times (5), SMOKE_DELAY_SECONDS apart (5), because services-stable
# can answer a moment before the load balancer counts the new target healthy, and each request
# gives up after 10 seconds. A check that still fails exits 1.
#
# Each app repository supplies its own smoke.sh, with its own host and checks: deploy.sh only calls
# $script_dir/smoke.sh, and knows nothing of this file's host.
set -euo pipefail

: "${ALB_DNS_NAME:?ALB_DNS_NAME is required}"
host=opendoor.jameslittlefield.net
attempts="${SMOKE_ATTEMPTS:-5}"
delay="${SMOKE_DELAY_SECONDS:-5}"

# The body, then the status code on a line of its own. The address goes last.
fetch() {
  curl -sS --max-time 10 --connect-to "$host:443:$ALB_DNS_NAME:443" \
    -w '\n%{http_code}' "https://$host$1"
}

# The things a body is checked for, read from stdin. The readiness check needs only the 200.
anything() { cat >/dev/null; }
the_web_app() { grep -qF '<div id="root">'; }
the_availability() { jq -e 'type == "object" and has("available")' >/dev/null; }

# check <path> <body check>: 200, and a body that passes.
check() {
  local path="$1" body_check="$2" attempt response
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if response="$(fetch "$path")" &&
      [[ "${response##*$'\n'}" == 200 ]] &&
      "$body_check" <<<"${response%$'\n'*}" 2>/dev/null; then
      echo "PASS: GET $path"
      return 0
    fi
    if ((attempt < attempts)); then sleep "$delay"; fi
  done
  echo "FAIL: GET $path did not answer 200 with the expected body after $attempts attempts" >&2
  return 1
}

check / the_web_app
check /api/v1/health anything
check /api/v1/assistant/availability the_availability
