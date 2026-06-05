"""
Slack API route — POST /slack/events

Receives all Slack payloads (slash commands, block actions, modal submissions)
and dispatches through the Slack Bolt App via AsyncSlackRequestHandler.

Slack Bolt automatically verifies X-Slack-Signature (HMAC-SHA256) before
any handler is invoked — no manual signature check needed here.

Supported slash commands
------------------------
  /주간보고   -> WriteReportHandler  (opens write_report_modal)
  /취합       -> AggregateReportHandler  (팀장 전용)
  /보고대상   -> AssignReportersHandler  (팀장 전용)
  /팀장등록   -> RegisterTeamLeadHandler

Environment variables required
------------------------------
    SLACK_BOT_TOKEN      -- xoxb-... Bot User OAuth Token
    SLACK_SIGNING_SECRET -- App Signing Secret (Basic Information)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from src.adapters.slack.slack_handler import get_slack_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

_handler = AsyncSlackRequestHandler(get_slack_app())


@router.post("/events")
async def slack_events(req: Request) -> Response:
    """
    POST /slack/events

    Single endpoint for all Slack interactions:
    - Slash commands  (/주간보고, /취합, /보고대상, /팀장등록)
    - Block Kit button actions
    - Modal view submissions (write_report_modal, assign_reporters_modal)
    """
    return await _handler.handle(req)
