# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.15 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_SYSTEM_CERTS=1 \
    PATH="/workspace/backend/.venv/bin:$PATH"

WORKDIR /workspace/backend

# Install the locked dependency graph before copying source for better layer reuse.
COPY backend/pyproject.toml backend/uv.lock ./
RUN set -eu; \
    for attempt in 1 2 3 4 5; do \
      if uv sync --frozen --no-dev --no-install-project; then exit 0; fi; \
      echo "uv dependency sync failed (attempt ${attempt}/5); retrying"; \
    done; \
    exit 1

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
COPY backend/evaluation ./evaluation
COPY sample_data ../sample_data

# The application is executed from this worktree, so the dependency layer does not need
# to rebuild/install the editable project a second time after the source files are copied.
RUN set -eu; \
    for attempt in 1 2 3 4 5; do \
      if uv sync --frozen --no-dev --no-install-project; then break; fi; \
      echo "uv project sync failed (attempt ${attempt}/5); retrying"; \
      if [ "$attempt" = "5" ]; then exit 1; fi; \
    done \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /workspace/data/runtime/demo \
    && chown -R appuser:appuser /workspace

USER appuser
EXPOSE 8000

# Compose runs migrations/seeding before this server command in Demo Mode.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
