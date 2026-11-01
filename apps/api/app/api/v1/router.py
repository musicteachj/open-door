"""Every version 1 endpoint, mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import health
from app.modules.assistant import routes as assistant
from app.modules.cases import routes as cases
from app.modules.console import routes as console
from app.modules.handbook import routes as handbook
from app.modules.identity import routes as identity
from app.modules.people import routes as people
from app.modules.sandbox import routes as sandbox
from app.modules.timeoff import routes as timeoff

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(sandbox.router)
api_router.include_router(identity.router)
api_router.include_router(people.router)
api_router.include_router(handbook.router)
api_router.include_router(assistant.router)
api_router.include_router(timeoff.router)
api_router.include_router(cases.router)
api_router.include_router(console.router)
