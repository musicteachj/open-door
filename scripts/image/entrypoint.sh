#!/bin/sh
# The image's entrypoint. `exec` makes uvicorn PID 1, so SIGTERM reaches it and it drains.
#
# FORWARDED_ALLOW_IPS names the addresses whose X-Forwarded-For uvicorn may trust (the load
# balancer's). Empty or unset must mean "trust no proxy". uvicorn alone would read the variable, or
# fall back to 127.0.0.1,::1 when it is unset (harmless inside a container, but not "none"). So an
# empty or unset value is exported as empty, which uvicorn reads as an empty trusted list, and the
# flag is passed only when there is a value.
#
# PORT is the port uvicorn listens on (8000 when unset). The deploy never sets it. The test runs do,
# because on Linux the container shares the host's network and must not take :8000 from `make dev`.
#
# --timeout-keep-alive 130 keeps an idle connection open longer than the load balancer's idle
# timeout (at least 120 seconds, Phase 9), so the load balancer, not uvicorn, closes idle
# connections. With uvicorn's default of 5 seconds, a request the load balancer sends just as
# uvicorn closes the connection fails as a 502. Raise it if the idle timeout ever goes above 120.
set -eu

PORT="${PORT:-8000}"
# HOST is the address uvicorn binds (0.0.0.0 when unset, which the deploy and a published port
# need). The Linux test runs share the host's network, so they bind a narrower address.
HOST="${HOST:-0.0.0.0}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-}"
export FORWARDED_ALLOW_IPS

set -- --factory app.main:create_app --host "$HOST" --port "$PORT" \
  --proxy-headers --no-server-header --timeout-graceful-shutdown 15 --timeout-keep-alive 130
if [ -n "$FORWARDED_ALLOW_IPS" ]; then
  set -- "$@" --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
fi
exec uvicorn "$@"
