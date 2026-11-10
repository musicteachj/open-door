"""Serve the built web app from the API, so one image is one origin (ADR 0020).

Only when `WEB_DIST_DIR` is set (the production image sets it). In development Vite serves the web
app and the API serves nothing outside /api/.

- `/assets/*`: hashed files, cached for a year. A missing asset is a 404, never the page.
- A real file in the dist root (the favicon, the manifest): served with a short cache.
- Every other GET or HEAD outside /api/: `index.html`, rendered per response with a fresh nonce
  (in the CSP header and in `<meta name="csp-nonce">`) and the Turnstile site key, never cached.
- An unknown /api/ path stays the JSON problem 404.
"""

import html
import re
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.api_paths import API_PREFIX, is_api_request, route_path
from app.core.cache_control import CACHE_CONTROL_HEADER, NO_STORE
from app.core.config import Settings
from app.core.security_headers import content_security_policy

ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
FILE_CACHE_CONTROL = "public, max-age=3600"
INDEX_NAME = "index.html"
NONCE_BYTES = 16

# The two placeholders `apps/web/index.html` carries, empty, which Vite's build keeps.
NONCE_META = re.compile(r'<meta\s+name="csp-nonce"\s+content=""\s*/?>')
SITE_KEY_META = re.compile(r'<meta\s+name="turnstile-site-key"\s+content=""\s*/?>')


def load_index(dist_dir: Path) -> str:
    """The built page, or a refusal to start if it is missing or lacks a placeholder."""
    index = dist_dir / INDEX_NAME
    if not index.is_file():
        msg = f"WEB_DIST_DIR has no {INDEX_NAME}: {dist_dir}"
        raise ValueError(msg)
    text = index.read_text(encoding="utf-8")
    for name, pattern in (("csp-nonce", NONCE_META), ("turnstile-site-key", SITE_KEY_META)):
        if pattern.search(text) is None:
            msg = f'{INDEX_NAME} has no empty <meta name="{name}" content=""> placeholder'
            raise ValueError(msg)
    return text


def render_index(template: str, *, nonce: str, site_key: str) -> str:
    """The page for one response. The values are escaped, and substituted by function so a
    backslash in a key is never read as a regex group reference."""
    with_nonce = NONCE_META.sub(
        lambda _: f'<meta name="csp-nonce" content="{html.escape(nonce)}" />', template, count=1
    )
    return SITE_KEY_META.sub(
        lambda _: f'<meta name="turnstile-site-key" content="{html.escape(site_key)}" />',
        with_nonce,
        count=1,
    )


def not_found() -> Response:
    """A plain 404 that no cache keeps (a hashed asset missing during a deploy must not stick)."""
    return Response("Not Found", status_code=404, headers={CACHE_CONTROL_HEADER: NO_STORE})


def has_hidden_part(path: str) -> bool:
    """A path part starting with a dot (`..`, `.vite/manifest.json`, a stray `.gitkeep`): never a
    file the app needs, so nothing hidden is served. `..` is refused again by the resolve check."""
    return any(part.startswith(".") for part in path.split("/"))


class ImmutableAssets:
    """Wraps `StaticFiles` (which has its own traversal guard) to add the long cache header to the
    files it serves. Pure ASGI, so a file stream isn't buffered; errors get no cache header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_cache(message: Message) -> None:
            if message["type"] == "http.response.start":
                # A file is cached for a year; anything else (a 404 for a hashed name that a
                # newer deploy hasn't shipped yet) is never cached.
                ok = message["status"] in (200, 206, 304)
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                headers[CACHE_CONTROL_HEADER] = ASSET_CACHE_CONTROL if ok else NO_STORE
            await send(message)

        if has_hidden_part(scope.get("path", "")):
            await not_found()(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send_with_cache)
        except HTTPException as exc:
            # StaticFiles raises its 404 (and a 405) rather than sending it; answer it here, so it
            # carries no-store instead of reaching the problem handler with no cache header.
            await Response(
                status_code=exc.status_code,
                headers={CACHE_CONTROL_HEADER: NO_STORE, **(exc.headers or {})},
            )(scope, receive, send)


def _file_inside(root: Path, relative: str) -> Path | None:
    """The file `relative` names under `root`, or None. `..`, encoded forms (already decoded by the
    server), and symlinks that leave the root all resolve outside it and are refused."""
    try:
        candidate = (root / relative).resolve()
    except (OSError, ValueError):  # a NUL byte, or a loop
        return None
    if not candidate.is_relative_to(root) or candidate == root / INDEX_NAME:
        return None
    return candidate if candidate.is_file() else None


def install_web_app(app: FastAPI, settings: Settings) -> None:
    """Mount /assets and make the page server the router's fallback (it runs only when no route
    matched). Does nothing without WEB_DIST_DIR."""
    if settings.web_dist_dir is None:
        return
    root = settings.web_dist_dir.resolve()
    template = load_index(root)
    site_key = settings.turnstile_site_key

    def page() -> HTMLResponse:
        nonce = secrets.token_urlsafe(NONCE_BYTES)
        return HTMLResponse(
            render_index(template, nonce=nonce, site_key=site_key),
            headers={
                CACHE_CONTROL_HEADER: NO_STORE,
                "Content-Security-Policy": content_security_policy(nonce),
            },
        )

    # A build always has assets; without the folder StaticFiles would raise on every request.
    if not (root / "assets").is_dir():
        msg = f"WEB_DIST_DIR has no assets folder: {root}"
        raise ValueError(msg)
    files = StaticFiles(directory=root / "assets")
    app.mount("/assets", ImmutableAssets(files), name="assets")

    fallback = app.router.default

    async def web_app(scope: Scope, receive: Receive, send: Send) -> None:
        """The router's fallback: it runs only when no route matched, so every /api/ path keeps
        exactly the 404 or 405 it had before, and other methods get the router's 404."""
        if (
            scope["type"] != "http"
            or is_api_request(scope)
            or route_path(scope) == API_PREFIX.rstrip("/")
            or scope["method"] not in ("GET", "HEAD")
        ):
            await fallback(scope, receive, send)
            return
        response = respond(route_path(scope).lstrip("/"))
        await response(scope, receive, send)

    def respond(full_path: str) -> Response:
        if full_path in ("", INDEX_NAME):
            return page()
        if "\x00" in full_path or has_hidden_part(full_path):
            return not_found()
        found = _file_inside(root, full_path)
        if found is not None:
            return FileResponse(found, headers={CACHE_CONTROL_HEADER: FILE_CACHE_CONTROL})
        return page()

    app.router.default = web_app
