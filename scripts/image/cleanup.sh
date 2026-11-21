#!/bin/sh
# The scheduled cleanup: delete expired sandboxes, old spend rows and start counts, and unused
# handbook versions. It reads only CLEANUP_DATABASE_URL. Takes no argument: it is the image's
# entrypoint for this job (`docker run --entrypoint /app/cleanup.sh`). Like the API's entrypoint,
# it exits 64 on any argument, so a stray `command` in a task definition fails loudly.
set -eu

if [ "$#" -gt 0 ]; then
  echo "The cleanup job takes no command (got: $1)." >&2
  exit 64
fi

cd /app/apps/api
exec python -m app.jobs.cleanup
