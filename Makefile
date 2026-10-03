# Open Door developer commands. Run `make` to list them.
# Written for GNU Make 3.81, the version macOS ships: each recipe line runs in its own shell, so
# every line that needs a directory starts with `cd`.

API := apps/api
WEB := apps/web

.DEFAULT_GOAL := help
.PHONY: help setup db db-stop migrate dev dev-api dev-web openapi check check-api check-web

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install API and web dependencies; create apps/api/.env if it's missing
	cd $(API) && uv sync
	cd $(WEB) && npm ci
	@test -f $(API)/.env || (cp $(API)/.env.example $(API)/.env && echo "Created $(API)/.env")

db: ## Start the development Postgres in Docker and wait until it's ready
	docker compose up --detach --wait db

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

dev: db migrate ## Start Postgres, migrate, then run the API (:8000) and the web app (:5173)
	$(MAKE) -j2 dev-api dev-web

dev-api: ## Run only the API, with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

dev-web: ## Run only the web app
	cd $(WEB) && npm run dev

openapi: ## Regenerate the OpenAPI schema and the web app's API client
	cd $(API) && uv run python scripts/export_openapi.py
	cd $(WEB) && npm run generate:api

check: check-api check-web ## Run everything CI runs (start Postgres first with `make db`)

check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python scripts/export_openapi.py --check

check-web: ## Lint, format-check, type-check, test, and build the web app; confirm the client
	cd $(WEB) && npm run lint
	cd $(WEB) && npm run format:check
	cd $(WEB) && npm run typecheck
	cd $(WEB) && npm test
	cd $(WEB) && npm run build
	cd $(WEB) && npm run check:api-client
