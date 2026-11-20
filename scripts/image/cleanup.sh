#!/bin/sh
# The scheduled cleanup: delete expired sandboxes, old spend rows and start counts, and unused
# handbook versions. It reads only CLEANUP_DATABASE_URL. Takes no argument: it is the image's
# entrypoint for this job (`docker run --entrypoint /app/cleanup.sh`).
set -eu
cd /app/apps/api
exec python -m app.jobs.cleanup
