# Callwise backend — one image, many entrypoints (control-api / webhook-ingest / workers).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# uv: fast, reproducible installs from the pinned pyproject / uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer) — copy lockfiles only.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project --no-dev

# Now the source.
COPY . .
RUN uv sync --no-dev

EXPOSE 8000 8001

# Default entrypoint; compose / k8s override `command` per deployment.
CMD ["uv", "run", "uvicorn", "callwise.control_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
