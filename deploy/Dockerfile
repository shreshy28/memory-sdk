FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/
WORKDIR /workspace

COPY pyproject.toml uv.lock README.md ./
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY packages packages
RUN uv sync --frozen --all-packages --no-dev

ENV PATH="/workspace/.venv/bin:$PATH"
