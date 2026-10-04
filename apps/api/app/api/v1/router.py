"""Every version 1 endpoint, mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import health
from app.modules.identity import routes as identity
from app.modules.sandbox import routes as sandbox

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(sandbox.router)
api_router.include_router(identity.router)
