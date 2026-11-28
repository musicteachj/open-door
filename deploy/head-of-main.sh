#!/usr/bin/env bash
# Refuses (exit 1) unless this run's commit is the current head of main. The deploy job runs it twice,
# once before it takes AWS credentials and once right before the image is pushed.
#
# "Re-run jobs" on an older run keeps that run's commit, and an older run approved late can land after a
# newer one. Either would put old code over a newer release, so only the commit at the head of main
# deploys. A run by hand on main starts from the head, so it passes.
#
# Reads RUN_SHA (the run's commit), REPO (owner/name) and GH_TOKEN (for `gh`) from the environment.
set -euo pipefail

: "${RUN_SHA:?RUN_SHA is required}"
: "${REPO:?REPO is required}"

head="$(gh api "repos/$REPO/branches/main" --jq .commit.sha)"
if [[ "$head" != "$RUN_SHA" ]]; then
  echo "This run is for $RUN_SHA, but main is now $head. If a newer run exists, it deploys main's head; otherwise run the workflow by hand on main." >&2
  exit 1
fi
