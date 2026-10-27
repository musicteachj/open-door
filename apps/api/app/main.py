"""The application factory. Run it with `uvicorn --factory app.main:create_app`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.ai import anthropic_transport
from app.ai.case_summary import Summarizer
from app.ai.embeddings import Embedder, QueryEmbeddingLru, VoyageEmbedder
from app.ai.scripted import ScriptedSummarizer, ScriptedTransport
from app.ai.transport import Transport, require_a_transport_fit_for
from app.api.problems import document_problems_as_problem_json
from app.api.v1.router import api_router
from app.core.cache_control import NoStoreMiddleware
from app.core.config import Settings, get_settings
from app.core.encryption import LocalKeyProvider, load_key_provider
from app.core.logging import configure_logging
from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.db.engine import create_engine
from app.modules.assistant.sse import CLOSE_TIMEOUT_SECONDS, StreamTracker
from app.modules.identity.same_origin import SameOriginMiddleware

# How long the shutdown waits for open turn streams to save their turns before it closes the
# database engine. It is a stream's own close bound plus a second, so a cleanup that is still inside
# its bound finishes, and a stuck one cannot hold the shutdown for good.
STREAM_DRAIN_SECONDS = CLOSE_TIMEOUT_SECONDS + 1.0

logger = logging.getLogger(__name__)


def _build_transport(settings: Settings) -> Transport:
    if settings.ai_transport == "anthropic":
        return anthropic_transport.from_settings(settings)
    return ScriptedTransport()


def _build_summarizer(settings: Settings) -> Summarizer | None:
    """The case summarizer. Every transport but `anthropic` gets the scripted one. Under
    `anthropic` there is none until Stage 4 adds the real one: the API still starts, and each
    summary is recorded as failed with `transport`."""
    if settings.ai_transport == "anthropic":
        return None
    return ScriptedSummarizer()


def _build_embedder(settings: Settings) -> Embedder | None:
    """Query embeddings cost money, so only the anthropic transport with a Voyage key gets one.

    Without one the handbook search is full-text only. This keeps `make dev` and the browser tests
    free even when the developer's `.env` holds a Voyage key for `make embed`.
    """
    if settings.ai_transport != "anthropic" or settings.voyage_api_key is None:
        return None
    return QueryEmbeddingLru(VoyageEmbedder(settings.voyage_api_key))


def build_key_provider(settings: Settings) -> LocalKeyProvider:
    """The one key provider, or a refusal to start: no keyring, a keyring file others can read,
    or the fake test key outside APP_ENV=test. There is no default key."""
    keyring = settings.encryption_keyring
    keyring_file = settings.encryption_keyring_file
    keys = load_key_provider(
        keyring=None if keyring is None else keyring.get_secret_value(),
        keyring_file=None if keyring_file is None else keyring_file.get_secret_value(),
    )
    if keys.uses_test_key and settings.app_env != "test":
        msg = "The keyring holds the test key, which only APP_ENV=test accepts. Run `make keyring`."
        raise ValueError(msg)
    return keys


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings are validated here, so a bad environment fails at boot."""
    if settings is None:
        settings = get_settings()
    configure_logging(settings.log_level)
    require_a_transport_fit_for(settings)
    if settings.ai_transport == "replay":
        msg = (
            "AI_TRANSPORT=replay is for the eval harness only: it keeps per-item state and has no"
            " fixture-path setting. Use scripted or anthropic for the app."
        )
        raise ValueError(msg)
    keys = build_key_provider(settings)
    # Refused here so a bad environment fails at boot. The transport itself is built in the
    # lifespan, with the client it closes, so each lifespan run gets its own.
    if settings.ai_transport == "anthropic":
        anthropic_transport.require_an_api_key(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        transport = _build_transport(settings)
        app.state.engine = create_engine(str(settings.database_url))
        app.state.transport = transport
        app.state.embedder = _build_embedder(settings)
        app.state.summarizer = _build_summarizer(settings)
        streams = StreamTracker()
        app.state.streams = streams
        try:
            yield
        finally:
            try:
                # uvicorn cancels the requests still open when its graceful-shutdown timeout
                # passes, and then runs this shutdown without waiting for them. A canceled turn
                # stream saves its turn as `stopped` with a cleanup that needs the engine, so the
                # engine is closed only after the streams have finished (or the wait runs out).
                if not await streams.wait_until_idle(STREAM_DRAIN_SECONDS):
                    logger.error(
                        "%d turn stream(s) did not close before shutdown", streams.open_count
                    )
                # The Anthropic client holds a connection pool; the scripted transport has none.
                # Voyage needs nothing: it opens a client per call.
                if isinstance(transport, anthropic_transport.AnthropicTransport):
                    await transport.client.close()
            finally:
                await app.state.engine.dispose()

    app = FastAPI(title="Open Door API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.keys = keys
    # The middleware added last runs first. The request-ID middleware wraps the same-origin check,
    # so even a refused request carries its ID, and the no-store middleware wraps both, so a refusal
    # carries `Cache-Control: no-store` too. There is no CORS middleware: the web app reaches the
    # API on the same origin, so the browser blocks every cross-origin read by default.
    app.add_middleware(SameOriginMiddleware, app_origin=settings.app_origin)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(NoStoreMiddleware)
    install_problem_handlers(app)
    document_problems_as_problem_json(app)
    app.include_router(api_router)
    return app
