"""
Slack Bolt App setup — registers all slash commands, actions, and view submissions.

Replaces the Teams BotFrameworkAdapter + WeeklyReportBot pattern.
All Slack events hit POST /slack/events, which is handled by SlackRequestHandler
in src/api/routes/slack.py.

Slack App permissions required
-------------------------------
  chat:write          — post messages to channels
  chat:write.public   — post to channels the bot hasn't joined
  channels:read       — list channels
  users:read          — look up user info
  commands            — slash commands
  im:write            — send DMs
"""

from __future__ import annotations

import logging

from slack_bolt.async_app import AsyncApp

from src.infra.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ---------------------------------------------------------------------------
# Slack Bolt App singleton
# ---------------------------------------------------------------------------

slack_app = AsyncApp(
    token=_settings.slack_bot_token,
    signing_secret=_settings.slack_signing_secret,
)

# ---------------------------------------------------------------------------
# Slash command registrations
# ---------------------------------------------------------------------------

@slack_app.command("/주간보고")
async def cmd_write_report(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.write_report import WriteReportHandler
    await WriteReportHandler().handle(body=body, client=client, logger=logger)


@slack_app.command("/취합")
async def cmd_aggregate(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle(body=body, client=client, logger=logger)


@slack_app.command("/보고대상")
async def cmd_assign_reporters(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.assign_reporters import AssignReportersHandler
    await AssignReportersHandler().handle(body=body, client=client, logger=logger)


@slack_app.command("/팀장등록")
async def cmd_register_lead(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.register_team_lead import RegisterTeamLeadHandler
    await RegisterTeamLeadHandler().handle(body=body, client=client, logger=logger)


# ---------------------------------------------------------------------------
# Modal (view) submission handlers
# ---------------------------------------------------------------------------

@slack_app.view("write_report_modal")
async def handle_write_report_modal(ack, body, client, view, logger):
    """Handle report form submission from the write_report modal."""
    await ack()
    from src.adapters.slack.handlers.write_report import WriteReportHandler
    await WriteReportHandler().handle_modal_submit(
        body=body, client=client, view=view, logger=logger
    )


@slack_app.view("assign_reporters_modal")
async def handle_assign_reporters_modal(ack, body, client, view, logger):
    """Handle reporter assignment form submission."""
    await ack()
    from src.adapters.slack.handlers.assign_reporters import AssignReportersHandler
    await AssignReportersHandler().handle_modal_submit(
        body=body, client=client, view=view, logger=logger
    )


# ---------------------------------------------------------------------------
# Button action handlers
# ---------------------------------------------------------------------------

@slack_app.action("aggregate_confirm")
async def handle_aggregate_confirm(ack, body, client, logger):
    """Team lead confirms aggregation and triggers mail draft."""
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle_confirm_action(
        body=body, client=client, logger=logger
    )


def get_slack_app() -> AsyncApp:
    """Return the shared Slack Bolt app instance."""
    return slack_app
