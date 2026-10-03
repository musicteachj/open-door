# Open Door developer commands. Run `make` to list them.
# Written for GNU Make 3.81, the version macOS ships: each recipe line runs in its own shell, so
# every line that needs a directory starts with `cd`.

API := apps/api

.DEFAULT_GOAL := help
.PHONY: help db db-stop migrate dev-api openapi check-api

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

db: ## Start the development Postgres in Docker and wait until it's ready
	docker compose up --detach --wait db

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

dev-api: ## Run the API on http://localhost:8000 with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

openapi: ## Regenerate apps/web/openapi.json from the API
	cd $(API) && uv run python scripts/export_openapi.py

check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python scripts/export_openapi.py --check
