# Open Door developer commands. Run `make` to list them.
# Written for GNU Make 3.81, the version macOS ships: each recipe line runs in its own shell, so
# every line that needs a directory starts with `cd`.

API := apps/api
WEB := apps/web

# Linters and scanners run through uvx or Docker. Dependabot can't see these versions, so bump them
# by hand. GITLEAKS matches the version the Security workflow downloads.
TYPOS := typos@1.50.3
LYCHEE := lycheeverse/lychee:0.24.2
ACTIONLINT := rhysd/actionlint:1.7.12
ZIZMOR := zizmor@1.30.1
GITLEAKS := ghcr.io/gitleaks/gitleaks:v8.30.1

.DEFAULT_GOAL := help
.PHONY: help setup db db-stop migrate bootstrap-db ingest embed eval-retrieval eval-offline eval-live migrations-roundtrip dev dev-api dev-web openapi check check-api check-web e2e proxy-check captures check-docs check-workflows audit

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'

setup: ## Install dependencies and git hooks; create apps/api/.env if it's missing
	cd $(API) && uv sync
	cd $(WEB) && npm ci
	uvx pre-commit install
	@test -f $(API)/.env || (cp $(API)/.env.example $(API)/.env && echo "Created $(API)/.env")

db: ## Start the development Postgres, apply migrations, create the login users, then load the handbook
	docker compose up --detach --wait db
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py
	cd $(API) && uv run python scripts/ingest_handbook.py ingest

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply new database migrations
	cd $(API) && uv run alembic upgrade head

bootstrap-db: ## Create or update the login users named in DATABASE_URL and CLEANUP_DATABASE_URL
	cd $(API) && uv run python scripts/bootstrap_db_users.py

ingest: ## Load and publish the handbook from handbook/ and its committed embeddings (needs `make db`)
	cd $(API) && uv run python scripts/ingest_handbook.py ingest

# The only command that calls Voyage. It reads VOYAGE_API_KEY from apps/api/.env; an empty value
# exported in the shell is ignored, so it can't hide the key.
embed: ## Fetch missing handbook and eval embeddings from Voyage (needs VOYAGE_API_KEY); commit the result
	cd $(API) && uv run python scripts/ingest_handbook.py embed

# Reads the committed query embeddings, so it needs no key and no network. After changing a question
# in evals/retrieval/dataset.yaml, run `make embed` first and commit the cache.
eval-retrieval: ## Score handbook search against the labeled questions (needs `make db`); see evals/README.md
	cd $(API) && uv run python ../../evals/retrieval/run.py

# Replays the recorded assistant answers through the real loop, tools, graders, and judge reading, so
# it needs no key and no network. A prompt, tool, or retrieval change makes a request miss its
# recording: re-record with `make eval-live YES=1`. Until the full run is recorded (Phase 4, Stage 6),
# only the smoke set has recordings. One run at a time.
eval-offline: ## Replay the recorded assistant evals (needs `make db`); no network. See evals/README.md
	cd $(API) && uv run python ../../evals/assistant/run.py --mode offline --set smoke --check

# PAID. Without YES=1 (exactly 1: YES=0 or YES=no still only prints) it prints the set, the item count, the estimated cost, and the cap, and calls
# nothing. SET=smoke (about $1.20, cap $2), SET=full (about $14, cap $16), or SET=effort (the smoke
# items at medium effort, about $1.50, cap $2; its recordings go to a git-ignored folder, and
# COMPARE=<a low-effort scoreboard> prints the two side by side). A run reuses the recordings it
# already has and calls only requests that changed. FRESH=1 calls everything live again. PRUNE=1
# (SET=full only) also drops the old recordings no item asked for, and implies FRESH=1: with
# `SET=full FRESH=1 PRUNE=1` the whole fixture set is replaced. Each run writes its scoreboard and
# traces into the git-ignored evals/assistant/runs/. The key is read from apps/api/.env (an empty
# one exported in the shell is ignored). One run at a time; don't start it in the middle of `make check`.
SET ?= smoke
STAMP := $(shell date -u +%Y%m%dT%H%M%SZ)
RUNS := ../../evals/assistant/runs
eval-live: ## PAID: record the assistant evals. SET=smoke|full|effort, YES=1 to run, COMPARE=<scoreboard.json>
	cd $(API) && uv run python ../../evals/assistant/run.py --mode live --set $(SET) \
		$(if $(filter effort,$(SET)),--fixtures-dir ../../evals/assistant/fixtures-effort) \
		$(if $(COMPARE),--compare $(abspath $(COMPARE))) \
		--json $(RUNS)/$(STAMP)-$(SET).json --traces $(RUNS)/$(STAMP)-$(SET)-traces.json \
		$(if $(or $(filter 1,$(FRESH)),$(filter 1,$(PRUNE))),--fresh) \
		$(if $(filter 1,$(PRUNE)),--prune) \
		$(if $(filter 1,$(YES)),--yes)

# Not part of check-api: it deletes every row, including the sandboxes you're working in.
migrations-roundtrip: ## Undo every migration, apply them again, recreate the logins, and reload the handbook (wipes data)
	cd $(API) && uv run alembic downgrade base
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py
	cd $(API) && uv run python scripts/ingest_handbook.py ingest

dev: db ## Run `make db`, then the API (:8000) and the web app (:5173) together
	$(MAKE) -j2 dev-api dev-web

dev-api: ## Run only the API, with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

dev-web: ## Run only the web app
	cd $(WEB) && npm run dev

openapi: ## Regenerate the OpenAPI schema and the web app's API client
	cd $(API) && uv run python scripts/export_openapi.py
	cd $(WEB) && npm run generate:api

check: check-api check-web e2e proxy-check check-docs check-workflows ## Run everything CI runs (start Postgres first with `make db`)

check-api: ## Lint, type-check, migrate, load the handbook, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check . ../../evals --config pyproject.toml
	cd $(API) && uv run ruff format --check . ../../evals --config pyproject.toml
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py
	cd $(API) && uv run python scripts/ingest_handbook.py ingest
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python ../../evals/retrieval/run.py --check
	cd $(API) && uv run python ../../evals/assistant/run.py --mode offline --set smoke --check
	cd $(API) && uv run python scripts/export_openapi.py --check

check-web: ## Lint, format-check, type-check, test, and build the web app; confirm the client
	cd $(WEB) && npm run lint
	cd $(WEB) && npm run format:check
	cd $(WEB) && npm run typecheck
	cd $(WEB) && npm test
	cd $(WEB) && npm run build
	cd $(WEB) && npm run check:no-gallery
	cd $(WEB) && npm run check:api-client

# Playwright starts the API (:8100) and a preview of the gallery build (dist-e2e/), reusing either
# if it is already running. It needs Postgres up with the login users: run `make db` first.
e2e: ## Run the browser tests in Chromium, against the real API and a build with the gallery
	cd $(WEB) && npx playwright install chromium
	cd $(WEB) && npm run e2e

# Runs the turn stream through nginx with a 20-second read timeout: the pass run (a 45-second
# silence that the heartbeat must carry), the control run (heartbeat off; nginx must cut it), and
# the shutdown run (SIGTERM mid-stream; the turn must be saved as stopped). It starts the API on
# :8200 and nginx on :8201 itself, with the scripted model, and needs Docker and the seeded
# database (`make db`). About two minutes; don't run it beside other database-heavy work.
proxy-check: ## Run the turn stream through a strict nginx: the pass, control, and shutdown runs (needs `make db` and Docker)
	cd $(API) && uv run python ../../scripts/proxy-check/check.py

# Local only: `make check` and CI never run it. The specimen pages load React and Babel from
# unpkg.com, so it needs a network. The screens start real sandboxes, so it needs Postgres up with
# the login users: run `make db` first.
captures: ## Photograph the build's gallery beside the design specimens; write apps/web/captures/index.html
	cd $(WEB) && npx playwright install chromium
	cd $(WEB) && npm run build:e2e
	cd $(WEB) && npx playwright test --config playwright.captures.config.ts
	@echo "Report: $(CURDIR)/$(WEB)/captures/index.html"

# gitleaks scans every commit; the pre-commit hook scans each commit's staged changes.
audit: ## Scan for leaked secrets and vulnerable dependencies (what the Security workflow runs)
	@test -d "$(CURDIR)/.git" || { echo "make audit needs a normal checkout: in a git worktree the container can't read the history."; exit 1; }
	docker run --rm -v "$(CURDIR):/repo:ro" $(GITLEAKS) git --redact --exit-code 1 /repo
	cd $(API) && uv run --with pip-audit pip-audit --skip-editable
	cd $(WEB) && npm audit --audit-level=high

check-docs: ## Check spelling (American English), links between files, and leftover placeholders
	uvx $(TYPOS)
	git ls-files --cached --others --exclude-standard -- '*.md' | docker run --rm -i -v "$(CURDIR):/input:ro" -w /input $(LYCHEE) --offline --no-progress --include-fragments --files-from -
	@if git grep --untracked -n -I -w -E 'T[O]DO|TB[D]|FIXM[E]|XX[X]|[Ll]orem [i]psum' -- '*.md'; then echo "Finish or remove the placeholders above."; exit 1; fi
	@if LC_ALL=C git grep --untracked -n -I -P '\xE2\x80\x94' -- . ':!docs/plans/2026-09-29-open-door-initial-plan.md' ':!docs/design/' ':!evals/**/fixtures/**' ':!*.lock' ':!**/package-lock.json'; then echo "Replace the em dashes above (CLAUDE.md, Writing)."; exit 1; fi

check-workflows: ## Check the GitHub Actions workflows for mistakes (actionlint) and security (zizmor)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT) -no-color
	uvx $(ZIZMOR) .
