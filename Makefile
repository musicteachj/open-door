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
.PHONY: help setup db db-stop migrate bootstrap-db migrations-roundtrip dev dev-api dev-web openapi check check-api check-web e2e captures check-docs check-workflows audit

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'

setup: ## Install dependencies and git hooks; create apps/api/.env if it's missing
	cd $(API) && uv sync
	cd $(WEB) && npm ci
	uvx pre-commit install
	@test -f $(API)/.env || (cp $(API)/.env.example $(API)/.env && echo "Created $(API)/.env")

db: ## Start the development Postgres, apply migrations, then create the login users
	docker compose up --detach --wait db
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply new database migrations
	cd $(API) && uv run alembic upgrade head

bootstrap-db: ## Create or update the login users named in DATABASE_URL and CLEANUP_DATABASE_URL
	cd $(API) && uv run python scripts/bootstrap_db_users.py

# Not part of check-api: it deletes every row, including the sandboxes you're working in.
migrations-roundtrip: ## Undo every migration, apply them again, and recreate the logins (wipes data)
	cd $(API) && uv run alembic downgrade base
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py

dev: db ## Run `make db`, then the API (:8000) and the web app (:5173) together
	$(MAKE) -j2 dev-api dev-web

dev-api: ## Run only the API, with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

dev-web: ## Run only the web app
	cd $(WEB) && npm run dev

openapi: ## Regenerate the OpenAPI schema and the web app's API client
	cd $(API) && uv run python scripts/export_openapi.py
	cd $(WEB) && npm run generate:api

check: check-api check-web e2e check-docs check-workflows ## Run everything CI runs (start Postgres first with `make db`)

check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
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

# Local only: `make check` and CI never run it. The specimen pages load React and Babel from
# unpkg.com, so it needs a network. It needs no database: the gallery is static.
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

check-workflows: ## Check the GitHub Actions workflows for mistakes (actionlint) and security (zizmor)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT) -no-color
	uvx $(ZIZMOR) .
