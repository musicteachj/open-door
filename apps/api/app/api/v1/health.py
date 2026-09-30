"""GET /api/v1/health: is the API up, and can it reach its database?"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app import __version__
from app.db.engine import ping

router = APIRouter(tags=["health"])

DatabasePing = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


def get_database_ping(request: Request) -> DatabasePing:
    """The database check, as a dependency so tests can replace it."""
    engine = request.app.state.engine

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
