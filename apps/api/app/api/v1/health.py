"""GET /api/v1/health: is the API up, and can it reach its database?"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.deps import get_engine
from app.db.engine import ping

router = APIRouter(tags=["health"])

DatabasePing = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


def get_database_ping(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> DatabasePing:
    """The database check, as a dependency so tests can replace it.

    It uses a bare connection, never a tenant session, so it stays independent of row-level
    security.
    """

    async def check() -> bool:
        return await ping(engine)

    return check


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Report whether the API and its database are up",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def get_health(
    response: Response,
    database_ping: Annotated[DatabasePing, Depends(get_database_ping)],
) -> HealthResponse:
    if await database_ping():
        return HealthResponse(status="ok", database="ok", version=__version__)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="unavailable", version=__version__)
