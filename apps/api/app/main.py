"""The application factory. Run it with `uvicorn --factory app.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1.router import api_router
from app.core.cache_control import NoStoreMiddleware
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.db.engine import create_engine
from app.modules.identity.same_origin import SameOriginMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings are validated here, so a bad environment fails at boot."""
    if settings is None:
        settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(str(settings.database_url))
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Open Door API", version=__version__, lifespan=lifespan)
    # The middleware added last runs first. The request-ID middleware wraps the same-origin check,
    # so even a refused request carries its ID, and the no-store middleware wraps both, so a refusal
    # carries `Cache-Control: no-store` too. There is no CORS middleware: the web app reaches the
    # API on the same origin, so the browser blocks every cross-origin read by default.
    app.add_middleware(SameOriginMiddleware, app_origin=settings.app_origin)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(NoStoreMiddleware)
    install_problem_handlers(app)
    app.include_router(api_router)
    return app
