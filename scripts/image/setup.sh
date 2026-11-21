#!/bin/sh
# The deploy's one-off setup: migrate, create the login users, load the handbook. Runs on every
# deploy, before the service updates; each step is safe to repeat. Takes no argument: it is the
# image's entrypoint for this job (`docker run --entrypoint /app/setup.sh`). Like the API's
# entrypoint, it exits 64 on any argument, so a stray `command` in a task definition fails loudly.
set -eu

if [ "$#" -gt 0 ]; then
  echo "The setup job takes no command (got: $1)." >&2
  exit 64
fi

cd /app/apps/api
alembic upgrade head
python scripts/bootstrap_db_users.py
exec python scripts/ingest_handbook.py ingest
