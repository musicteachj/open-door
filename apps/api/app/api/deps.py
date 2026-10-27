"""Dependencies the routes share."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.embeddings import Embedder
from app.ai.transport import Transport
from app.core.config import Settings
from app.core.encryption import KeyProvider
from app.modules.assistant.sse import StreamTracker


def get_engine(request: Request) -> AsyncEngine:
    """The engine the app's lifespan created.

    Without the lifespan there is no engine, and the request fails with a 500 whose logged cause
    says so, instead of an AttributeError from deep inside a route.
    """
    engine = getattr(request.app.state, "engine", None)
    if not isinstance(engine, AsyncEngine):
        msg = "No database engine: build the app with create_app() and run its lifespan."
        raise RuntimeError(msg)
    return engine


def get_transport(request: Request) -> Transport:
    """The model transport the app's lifespan built (scripted or anthropic)."""
    transport = getattr(request.app.state, "transport", None)
    if transport is None:
        msg = "No model transport: build the app with create_app() and run its lifespan."
        raise RuntimeError(msg)
    return transport  # type: ignore[no-any-return]


def get_embedder(request: Request) -> Embedder | None:
    """The query embedder, or None when the search is full-text only.

    None is a real answer (the scripted transport, or no Voyage key), so only a missing lifespan
    is an error.
    """
    if not hasattr(request.app.state, "embedder"):
        msg = "No embedder slot: build the app with create_app() and run its lifespan."
        raise RuntimeError(msg)
    return request.app.state.embedder  # type: ignore[no-any-return]


def get_app_settings(request: Request) -> Settings:
    """The settings the app was built with, so a route reads the same values the lifespan used."""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        msg = "No settings: build the app with create_app()."
        raise RuntimeError(msg)
    return settings


def get_streams(request: Request) -> StreamTracker:
    """The tracker of open turn streams the app's lifespan created."""
    streams = getattr(request.app.state, "streams", None)
    if not isinstance(streams, StreamTracker):
        msg = "No stream tracker: build the app with create_app() and run its lifespan."
        raise RuntimeError(msg)
    return streams


def get_keys(request: Request) -> KeyProvider:
    """The key provider the app built at boot, for sealing and opening encrypted text."""
    keys = getattr(request.app.state, "keys", None)
    if keys is None:
        msg = "No keyring: build the app with create_app(), which refuses to start without one."
        raise RuntimeError(msg)
    if not isinstance(keys, KeyProvider):
        msg = "app.state.keys is not a key provider."
        raise RuntimeError(msg)
    return keys


def utc_now() -> datetime:
    """The server's clock, as a dependency so a test can hold it still. Time-off writes and the
    assistant's confirm pass it to the time-off service as "now"."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(utc_now)]
