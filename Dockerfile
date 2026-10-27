# syntax=docker/dockerfile:1

# ---- build: resolve + install into a venv with uv (locked) ----
# Same python image as runtime so the venv's interpreter matches; Renovate bumps both together.
FROM python:3.15-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Install deps first (cached) using only the lockfile + manifest.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra otel

# Then install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra otel

# ---- runtime: slim image with just the venv ----
FROM python:3.15-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src

# non-root
RUN useradd --system --uid 1000 --create-home ambient2mqtt
USER 1000:1000

# /metrics, /healthz, /readyz (METRICS_PORT)
EXPOSE 9100

ENTRYPOINT ["ambient2mqtt"]
