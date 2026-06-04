"""Health check endpoint.

GET /health — returns 200 with DB connectivity probe.
Used by load balancers, container orchestrators, and uptime monitors.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", response_model=HealthResponse, summary="Liveness + DB probe")
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Return service liveness and database reachability.

    - ``status``: always ``"ok"`` when this endpoint responds.
    - ``db``: ``"ok"`` if a lightweight DB query succeeds, ``"error"`` otherwise.
    """
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        db_status = "error"

    return HealthResponse(status="ok", db=db_status)
