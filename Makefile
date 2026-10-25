.PHONY: lint typecheck test-unit architecture-check smoke-health db-reset migrate migration-check openapi-check ci

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

test-unit:
	uv run pytest tests/unit -q

architecture-check:
	uv run python scripts/architecture_check.py

smoke-health:
	uv run python scripts/smoke_health.py

db-reset:
	docker compose -f deploy/compose.yaml down -v
	docker compose -f deploy/compose.yaml up -d --wait database

migrate:
	uv run alembic -c packages/persistence-postgres/alembic.ini upgrade head

migration-check:
	uv run alembic -c packages/persistence-postgres/alembic.ini downgrade 0001_baseline
	uv run alembic -c packages/persistence-postgres/alembic.ini upgrade head

openapi-check:
	uv run python scripts/openapi_check.py

ci: lint typecheck test-unit architecture-check
