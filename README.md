# Memory SDK

Portable, local-first memory infrastructure for AI agents. This repository is a modular
monolith with independently runnable API, worker, console, and Python SDK surfaces.

## Local baseline

Prerequisites: Docker with Compose, `uv`, and `pnpm`.

```bash
cp deploy/env.example .env
docker compose -f deploy/compose.yaml up -d --build
make smoke-health
```

The API exposes liveness at `http://localhost:8000/health/live` and readiness at
`http://localhost:8000/health/ready`. The worker exposes corresponding endpoints on port
`8001`; worker readiness includes its database lease capability.

## Development

```bash
uv sync --all-packages --dev
make lint typecheck test-unit architecture-check
pnpm --dir apps/console install --frozen-lockfile
pnpm --dir apps/console build
```

Runtime configuration belongs to composition roots. Domain and application modules receive
typed ports and do not read environment variables.
