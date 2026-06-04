"""
Bot API route — POST /api/messages

This is the single endpoint that Microsoft Bot Framework calls for all
incoming bot activities (messages, invokes, etc.).

Security
--------
- Bot Framework JWT verification is handled by BotFrameworkHttpClient /
  botbuilder-integration-aiohttp's process_activity(). The adapter validates
  the Authorization header (Bearer token) against Microsoft's JWKS endpoint
  before our handler sees the activity.
- See ADR-SEC-007 for the JWT verification decision.

Registration
------------
Mount this router in src/api/app.py:
    from src.api.routes.bot import router as bot_router
    app.include_router(bot_router)

Environment variables required
-------------------------------
    MICROSOFT_APP_ID       — Bot's AAD app registration ID
    MICROSOFT_APP_PASSWORD — Bot's client secret
"""

from __future__ import annotations

import logging
import os

from aiohttp import web
from botbuilder.core import BotFrameworkAdapterSettings
from botbuilder.integration.aiohttp import BotFrameworkHttpAdapter

from src.adapters.teams.bot_handler import WeeklyReportBot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Adapter + Bot singletons (created once at module load)
# ---------------------------------------------------------------------------

_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

# ADR-SEC-007: empty APP_ID silently disables JWT verification — fail fast
if not _APP_ID:
    raise RuntimeError(
        "MICROSOFT_APP_ID environment variable is not set. "
        "Bot JWT verification would be disabled. Refusing to start."
    )

_adapter_settings = BotFrameworkAdapterSettings(
    app_id=_APP_ID,
    app_password=_APP_PASSWORD,
)
_adapter = BotFrameworkHttpAdapter(_adapter_settings)
_bot = WeeklyReportBot()


def get_adapter() -> BotFrameworkHttpAdapter:
    """Return the shared adapter instance (used by notification_jobs)."""
    return _adapter


def get_app_id() -> str:
    """Return the bot App ID (used by notification_jobs for proactive auth)."""
    return _APP_ID


# ---------------------------------------------------------------------------
# Error handler — logs unhandled exceptions without exposing internals
# ---------------------------------------------------------------------------

async def _on_error(context, error: Exception) -> None:
    logger.error("BotFrameworkAdapter unhandled error: %s", error, exc_info=True)
    # Do NOT reveal error details to the client
    try:
        from botbuilder.schema import Activity, ActivityTypes
        await context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text="처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            )
        )
    except Exception:
        pass  # Suppress secondary errors in the error handler


_adapter.on_turn_error = _on_error

# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

routes = web.RouteTableDef()


@routes.post("/api/messages")
async def messages(request: web.Request) -> web.Response:
    """
    POST /api/messages

    Receives all Bot Framework activities, verifies the JWT, and dispatches
    to WeeklyReportBot.on_turn().

    Returns HTTP 200 on success, 401 on auth failure (handled by adapter),
    500 on unexpected errors.
    """
    if "application/json" not in request.headers.get("Content-Type", ""):
        logger.warning("/api/messages: unexpected Content-Type: %s", request.headers.get("Content-Type"))

    try:
        response = await _adapter.process(request=request, bot=_bot)
        # BotFrameworkHttpAdapter.process() returns an aiohttp Response
        if response:
            return response
        return web.Response(status=200)
    except Exception as exc:
        logger.error("/api/messages unhandled exception: %s", exc, exc_info=True)
        return web.Response(status=500, text="Internal Server Error")


# ---------------------------------------------------------------------------
# aiohttp Application factory helper
# ---------------------------------------------------------------------------

def create_bot_app() -> web.Application:
    """
    Create a standalone aiohttp Application with only the bot route.

    For use in tests or when mounting the bot as a sub-application.
    The main app (src/api/app.py) should call app.add_routes(routes) instead.
    """
    app = web.Application()
    app.add_routes(routes)
    return app
