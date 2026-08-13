# syntax=docker/dockerfile:1

# ── Stage 1: build the frontend (Node) ──────────────────────────────────────
# Vite is configured (frontend/vite.config.ts) to emit to ../open_paxel/static,
# so building from /build/frontend produces /build/open_paxel/static.
FROM node:22-slim AS frontend

WORKDIR /build/frontend

# Install deps against the committed lockfile first for layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build the SPA → /build/open_paxel/static
COPY frontend/ ./
RUN npm run build


# ── Stage 2: runtime (Python + uv, no Node) ─────────────────────────────────
# Base image ships Python 3.12 (matches .python-version) with uv preinstalled.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

# uv settings: install into a project venv, copy (not symlink) from cache,
# and use the system-provided interpreter.
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first (cached unless lockfile/manifest change).
# README.md is referenced by pyproject (readme = "README.md") and is needed
# when the project itself is installed below.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Add the package source and install the project (editable), then drop in the
# prebuilt static assets so STATIC_DIR (open_paxel/static) resolves at runtime.
# assets/decision_catalog.json is force-included by hatchling (pyproject) and is
# also where catalog.py looks at runtime (project_root()/assets/...).
COPY open_paxel/ ./open_paxel/
COPY assets/decision_catalog.json ./assets/decision_catalog.json
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
COPY --from=frontend /build/open_paxel/static/ ./open_paxel/static/

# Non-root runtime user with a stable HOME. The host's ~/.claude is mounted
# read-only at $HOME/.claude (see docker-compose.yml); discovery reads
# Path.home()/.claude/projects. App data lives in OPEN_PAXEL_HOME (/data).
RUN useradd --create-home --home-dir /home/app --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /app /data /home/app
USER app
ENV HOME=/home/app \
    OPEN_PAXEL_HOME=/data

EXPOSE 3847

# Host binding is supplied by the environment (docker-compose sets
# OPEN_PAXEL_HOST=0.0.0.0); the code default stays 127.0.0.1. Reload is off in
# the container — there is no mounted source to watch.
CMD ["open-paxel", "serve", "--no-reload"]
