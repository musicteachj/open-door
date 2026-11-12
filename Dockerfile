# syntax=docker/dockerfile:1
# The Open Door production image: the API and the built web app, one origin (ADR 0020).
#
#   docker build -t open-door:prod .                      the production image (no component gallery)
#   docker build --build-arg GALLERY=true -t open-door:test .   the browser-test image
#
# Base images are pinned by tag and digest, read with `docker inspect` after `docker pull` on
# 2026-11-10. Dependabot's docker ecosystem needs the tag to propose updates of both.

# --- The web app ------------------------------------------------------------------------------
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS web
ARG GALLERY=false
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/web/ ./
# Only `vite build`, not `npm run build`: its `tsc -b` first type-checks the tests, which read files
# outside apps/web (evals/). CI type-checks the web app on its own. The gallery variant is built the
# way `npm run build:e2e` builds it (VITE_GALLERY), but into dist.
RUN if [ "$GALLERY" = "true" ]; then export VITE_GALLERY=true; fi; \
    npx vite build --outDir dist --emptyOutDir

# --- The API's virtual environment --------------------------------------------------------------
# ghcr.io/astral-sh/uv:python3.13-trixie-slim (the same Debian and Python as the final stage, so
# the environment's interpreter links resolve there).
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim@sha256:6ff812e34a0e14b4b8bc9ddf25e77b3e16bac6e0c4d9b67641f40366fa382d4c AS venv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
# Dependencies first, so a source change doesn't reinstall them.
RUN uv sync --locked --no-dev --no-install-project
# Then the project itself, editable at this same path in the final image: `app.__version__` reads
# the installed package's metadata, and the scripts and migrations run from the source directory.
COPY apps/api/ ./
RUN uv sync --locked --no-dev

# --- The final image ----------------------------------------------------------------------------
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

# The layout matters: scripts/ingest_handbook.py finds handbook/ three directories above itself.
# APP_ENV is production unless a run says otherwise (the test runs pass APP_ENV=test), so a deploy
# that forgets it refuses the development defaults (test keys, the development hash key) at start.
ENV PATH="/app/apps/api/.venv/bin:$PATH" \
    PYTHONPATH=/app/apps/api \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEB_DIST_DIR=/app/web-dist \
    APP_ENV=production

# The emSign roots (their intermediate keys were compromised, GHSA-6q48-6c7w-9gw2) must not be in the
# OS store, which the Anthropic SDK reads through truststore (httpx uses certifi, which dropped
# them in 2026.10.19). Debian's ca-certificates (20250419+deb13u1) still ships them, found by
# `make image-check` on 2026-11-10, so they are removed here and the store is rebuilt. The check
# keeps proving none come back.
RUN find /usr/share/ca-certificates -iname '*emsign*' -delete \
 && sed -i '/[Ee]m[Ss]ign/d' /etc/ca-certificates.conf \
 && update-ca-certificates --fresh

# The base image ships an empty root shell-history file; nothing of that kind belongs in the image.
RUN rm -f /root/.python_history /root/.bash_history

# A fixed uid, so a mounted volume or a task definition can name it.
RUN groupadd --system --gid 10001 opendoor \
 && useradd --system --uid 10001 --gid opendoor --no-create-home --shell /usr/sbin/nologin opendoor

COPY --from=venv /app/apps/api/.venv /app/apps/api/.venv
# .dockerignore keeps out tests, .env, .keys, and caches.
COPY apps/api/ /app/apps/api/
COPY handbook/ /app/handbook/
COPY --from=web /build/apps/web/dist /app/web-dist
COPY scripts/image/entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/entrypoint.sh

# PYTHONDONTWRITEBYTECODE stops the app writing .pyc files at run time (the user can't write
# there anyway), so compile the app's own modules once here; the venv's are compiled by uv.
RUN python -m compileall -q /app/apps/api/app

WORKDIR /app/apps/api
USER 10001:10001
EXPOSE 8000
# Reads HOST and PORT like the entrypoint, so a container bound to another address or port is still
# healthy (0.0.0.0, the default, is probed on the loopback).
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, sys, urllib.request; host = os.environ.get('HOST') or '127.0.0.1'; host = '127.0.0.1' if host in ('0.0.0.0', '::') else (f'[{host}]' if ':' in host else host); port = os.environ.get('PORT', '8000'); sys.exit(0 if urllib.request.urlopen(f'http://{host}:{port}/api/v1/health/live', timeout=3).status == 200 else 1)"]
ENTRYPOINT ["/app/entrypoint.sh"]
