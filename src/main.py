"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infra.config import get_settings
from src.infra.db import create_tables
from src.api.routes.health import router as health_router
from src.api.routes.scheduler import router as scheduler_router
from src.api.routes.slack import router as slack_router
from src.api.routes.admin import router as admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    settings = get_settings()

    logger.info("Starting Weekly Report Automation backend (Slack mode).")

    await create_tables()
    logger.info("Database tables verified.")

    yield

    logger.info("Shutting down Weekly Report Automation backend.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Weekly Report Automation",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(scheduler_router)
    app.include_router(slack_router)
    app.include_router(admin_router)

    return app


app = create_app()
