.PHONY: lint typecheck test-unit architecture-check smoke-health ci

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

ci: lint typecheck test-unit architecture-check
