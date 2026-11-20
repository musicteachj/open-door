#!/bin/sh
# The deploy's one-off setup: migrate, create the login users, load the handbook. Runs on every
# deploy, before the service updates; each step is safe to repeat. Takes no argument: it is the
# image's entrypoint for this job (`docker run --entrypoint /app/setup.sh`).
set -eu
cd /app/apps/api
alembic upgrade head
python scripts/bootstrap_db_users.py
exec python scripts/ingest_handbook.py ingest
