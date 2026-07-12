# syntax=docker/dockerfile:1
# Concierge for HA MCP — built locally by Supervisor from this Dockerfile.
# Multi-stage: Node builds the Lit frontend, uv builds the Python venv
# (backend + bundled ha-mcp), a slim runtime serves both via run.py.

# --- Stage 1: build the Lit frontend -> /fe/dist ---
FROM node:22-slim AS fe-build
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: build the backend venv (backend + ha-mcp) with uv ---
FROM ghcr.io/astral-sh/uv:0.11.27-python3.13-trixie-slim@sha256:68bbb9d4281aa16c9780820ceaf4c558d78fb65ce45d42eb589d7234e3f26e15 AS py-build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
COPY backend/concierge ./concierge
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Stage 3: runtime ---
FROM python:3.13-slim@sha256:3de9a8d7aedbb7984dc18f2dff178a7850f16c1ae7c34ba9d7ecc23d0755e35f
WORKDIR /app
COPY --from=py-build /app/.venv /app/.venv
COPY --from=fe-build /fe/dist /app/static
COPY run.py /run.py
ENV PATH="/app/.venv/bin:$PATH" \
    CONCIERGE_STATIC_DIR=/app/static \
    CONCIERGE_DATA_DIR=/data

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL \
    io.hass.name="Concierge for HA MCP (Dev)" \
    io.hass.description="Self-hosted chat concierge over ha-mcp, served via ingress" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}"

CMD ["python3", "/run.py"]
