# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.15 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/backend/.venv/bin:$PATH"

WORKDIR /workspace/backend

# Install the locked dependency graph before copying source for better layer reuse.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
COPY backend/evaluation ./evaluation
COPY sample_data ../sample_data

RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /workspace/data \
    && chown -R appuser:appuser /workspace

USER appuser
EXPOSE 8000

# Compose runs migrations/seeding before this server command in Demo Mode.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
