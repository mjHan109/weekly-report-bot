"""
Bot API route — POST /api/messages

Microsoft Bot Framework endpoint for all Teams activities.
Rewritten to use FastAPI (botbuilder.core.BotFrameworkAdapter) instead of
the aiohttp-specific BotFrameworkHttpAdapter.

JWT verification
----------------
- botbuilder's BotFrameworkAdapter validates the Authorization Bearer token
  against Microsoft's JWKS endpoint automatically.
- In dev mode (BOT_APP_ID == "dev-local" or empty), JWT verification is
  disabled so local testing works without Bot Framework credentials.

Environment variables
---------------------
    BOT_APP_ID       — Bot's AAD app registration ID (empty = dev mode)
    BOT_APP_PASSWORD — Bot's client secret
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bot"])

# ---------------------------------------------------------------------------
# Lazy-init singletons (avoid crashing at import time when creds are missing)
# ---------------------------------------------------------------------------

_adapter = None
_bot = None


def _init() -> None:
    """Initialize BotFrameworkAdapter + WeeklyReportBot once."""
    global _adapter, _bot
    if _adapter is not None:
        return

    from src.infra.config import get_settings
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
    from src.adapters.teams.bot_handler import WeeklyReportBot

    settings = get_settings()

    # Empty app_id disables JWT verification (dev mode).
    # "dev-local" sentinel from defaults → treat as empty.
    app_id = "" if settings.bot_app_id in ("dev-local", "") else settings.bot_app_id
    app_password = "" if settings.bot_app_password in ("dev-local", "") else settings.bot_app_password

    adapter_settings = BotFrameworkAdapterSettings(
        app_id=app_id,
        app_password=app_password,
    )
    _adapter = BotFrameworkAdapter(adapter_settings)
    _bot = WeeklyReportBot()

    async def _on_error(context, error: Exception) -> None:
        logger.error("BotFrameworkAdapter unhandled error: %s", error, exc_info=True)
        try:
            from botbuilder.schema import Activity, ActivityTypes
            await context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    text="처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                )
            )
        except Exception:
            pass

    _adapter.on_turn_error = _on_error
    logger.info(
        "BotFrameworkAdapter initialized | app_id=%s | jwt_verification=%s",
        app_id or "(empty — dev mode)",
        bool(app_id),
    )


def get_adapter():
    """Return the shared BotFrameworkAdapter (used by notification_jobs)."""
    _init()
    return _adapter


def get_app_id() -> str:
    """Return the bot App ID (used by notification_jobs for proactive auth)."""
    from src.infra.config import get_settings
    v = get_settings().bot_app_id
    return "" if v in ("dev-local", "") else v


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/api/messages")
async def messages(request: Request) -> Response:
    """
    POST /api/messages

    Receives all Bot Framework activities from Teams, verifies the JWT,
    and dispatches to WeeklyReportBot.on_turn().
    """
    try:
        _init()
    except Exception as exc:
        logger.error("Bot adapter init failed: %s", exc)
        return Response(status_code=503, content="Bot not configured")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        logger.warning("/api/messages: unexpected Content-Type: %s", content_type)
        return Response(status_code=415)

    try:
        body = await request.json()
    except Exception as exc:
        logger.warning("/api/messages: invalid JSON body: %s", exc)
        return Response(status_code=400)

    from botbuilder.schema import Activity

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    try:
        invoke_response = await _adapter.process_activity(
            activity, auth_header, _bot.on_turn
        )
        if invoke_response:
            return JSONResponse(
                content=invoke_response.body,
                status_code=invoke_response.status,
            )
        return Response(status_code=200)
    except Exception as exc:
        logger.error("/api/messages unhandled exception: %s", exc, exc_info=True)
        return Response(status_code=500)
