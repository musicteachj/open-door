"""The application factory. Run it with `uvicorn --factory app.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.db.engine import create_engine


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
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)
    app.include_router(api_router)
    return app
