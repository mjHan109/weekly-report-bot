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
    user_id = body["user_id"]
    channel_id = body["channel_id"]

    from src.adapters.slack.handlers.write_report import _is_designated_reporter, _is_past_deadline
    if not await _is_designated_reporter(user_id, channel_id):
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="보고 대상자가 아닙니다. 팀장에게 `/보고대상` 설정을 요청하세요.",
        )
        return

    is_late = await _is_past_deadline(channel_id)

    from src.adapters.slack.handlers.dm_report_flow import send_report_menu
    await send_report_menu(user_id=user_id, channel_id=channel_id, is_late=is_late, client=client)

    await client.chat_postEphemeral(
        channel=channel_id,
        user=user_id,
        text="📩 DM으로 주간 보고 메뉴를 보냈습니다.",
    )


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
    await ack()
    from src.adapters.slack.handlers.write_report import WriteReportHandler
    await WriteReportHandler().handle_modal_submit(body=body, client=client, view=view, logger=logger)


@slack_app.view("step_done")
async def handle_step_done(ack, view):
    from src.adapters.slack.handlers.write_report_steps import on_step1_submit
    await on_step1_submit(ack=ack, view=view)


@slack_app.view("step_inprogress")
async def handle_step_inprogress(ack, view):
    from src.adapters.slack.handlers.write_report_steps import on_step2_submit
    await on_step2_submit(ack=ack, view=view)


@slack_app.view("step_plan")
async def handle_step_plan(ack, view):
    from src.adapters.slack.handlers.write_report_steps import on_step3_submit
    await on_step3_submit(ack=ack, view=view)


@slack_app.view("step_confirm")
async def handle_step_confirm(ack, body, view, client):
    await ack()
    from src.adapters.slack.handlers.write_report_steps import on_confirm_submit
    await on_confirm_submit(view=view, user_id=body["user"]["id"], client=client)


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

@slack_app.action("write_report_modal_open")
async def action_modal_open(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.write_report import WriteReportHandler
    channel_id, is_late_str = body["actions"][0]["value"].split("|")
    is_late = is_late_str == "true"
    fake_body = {**body, "channel_id": channel_id, "user_id": body["user"]["id"], "trigger_id": body["trigger_id"]}
    await WriteReportHandler().handle(body=fake_body, client=client, logger=logger)


@slack_app.action("write_report_dm_open")
async def action_dm_open(ack, body, client, logger):
    await ack()
    channel_id, is_late_str = body["actions"][0]["value"].split("|")
    is_late = is_late_str == "true"
    from src.adapters.slack.handlers.write_report_steps import open_step1
    await open_step1(trigger_id=body["trigger_id"], channel_id=channel_id, is_late=is_late, client=client)


# ---------------------------------------------------------------------------
# DM conversational report flow
# ---------------------------------------------------------------------------

@slack_app.event("message")
async def handle_dm_message(event, client, logger):
    """Route incoming DM messages to the conversational report flow."""
    channel_type = event.get("channel_type")
    subtype = event.get("subtype")
    user_id = event.get("user")
    dm_channel = event.get("channel", "")
    text = event.get("text", "")

    logger.info(
        "message event | channel_type=%s subtype=%s user=%s channel=%s text_len=%d",
        channel_type, subtype, user_id, dm_channel, len(text),
    )

    if channel_type != "im":
        return
    if subtype is not None:
        return
    if not user_id or not text:
        return

    from src.adapters.slack.handlers.dm_report_flow import handle_dm_step
    handled = await handle_dm_step(user_id=user_id, dm_channel=dm_channel, text=text, client=client)
    if handled:
        logger.info("DM step handled | user=%s", user_id)
    else:
        logger.info("DM message ignored — no active flow | user=%s", user_id)


@slack_app.action("quick_write_start")
async def action_quick_write_start(ack, body, client, logger):
    """[빠른 작성] button — start conversational flow."""
    await ack()
    import json
    payload = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import start_quick_write
    await start_quick_write(
        user_id=user_id, dm_channel=dm_channel,
        channel_id=payload["channel_id"], is_late=payload["is_late"],
        client=client,
    )


@slack_app.action("load_last_week_dm")
async def action_load_last_week_dm(ack, body, client, logger):
    """[지난주 보고 불러오기] button — pre-fill from last week."""
    await ack()
    import json
    payload = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import load_last_week_and_confirm
    await load_last_week_and_confirm(
        user_id=user_id, dm_channel=dm_channel,
        channel_id=payload["channel_id"], is_late=payload["is_late"],
        client=client,
    )


@slack_app.action("quick_write_cancel")
async def action_quick_write_cancel(ack, body, client, logger):
    """[취소] button."""
    await ack()
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import clear_state
    clear_state(user_id)
    await client.chat_postMessage(channel=dm_channel, text="주간 보고 작성이 취소되었습니다.")


@slack_app.action("dm_report_submit")
async def action_dm_report_submit(ack, body, client, logger):
    """[제출] button on preview."""
    await ack()
    import json
    payload = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import submit_report
    # Update preview message first
    await client.chat_update(
        channel=dm_channel,
        ts=body["message"]["ts"],
        text="✅ 제출 완료",
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "✅ *제출되었습니다.*"}}],
    )
    await submit_report(user_id=user_id, dm_channel=dm_channel, payload=payload, client=client)


@slack_app.action("dm_report_edit")
async def action_dm_report_edit(ack, body, client, logger):
    """[수정] button on preview — restart from step 1."""
    await ack()
    import json
    payload = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import set_state
    # Restart flow but keep existing data as starting point
    set_state(user_id, "step_done", payload["channel_id"], payload["is_late"], payload.get("data", {}))
    await client.chat_update(
        channel=dm_channel,
        ts=body["message"]["ts"],
        text="수정 중...",
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "↩️ 다시 작성합니다."}}],
    )
    from src.adapters.slack.handlers.dm_report_flow import STEP_PROMPTS
    await client.chat_postMessage(
        channel=dm_channel,
        text=STEP_PROMPTS["step_done"],
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": STEP_PROMPTS["step_done"]}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "1 / 3단계"}]},
        ],
    )


@slack_app.action("edit_step_done")
async def action_edit_done(ack, body, client):
    await ack()
    import json
    meta = body["actions"][0]["value"]
    m = json.loads(meta)
    from src.adapters.slack.handlers.write_report_steps import build_step1
    await client.views_update(
        view_id=body["view"]["id"],
        view=build_step1(m["channel_id"], m["is_late"], m["data"].get("완료한 업무", "")),
    )


@slack_app.action("edit_step_inprogress")
async def action_edit_inprogress(ack, body, client):
    await ack()
    import json
    meta = body["actions"][0]["value"]
    m = json.loads(meta)
    from src.adapters.slack.handlers.write_report_steps import build_step2
    await client.views_update(
        view_id=body["view"]["id"],
        view=build_step2(m["channel_id"], m["is_late"], m["data"], m["data"].get("진행 중인 업무", "")),
    )


@slack_app.action("edit_step_plan")
async def action_edit_plan(ack, body, client):
    await ack()
    import json
    meta = body["actions"][0]["value"]
    m = json.loads(meta)
    from src.adapters.slack.handlers.write_report_steps import build_step3
    await client.views_update(
        view_id=body["view"]["id"],
        view=build_step3(m["channel_id"], m["is_late"], m["data"], m["data"].get("다음 주 계획", "")),
    )


@slack_app.action("aggregate_confirm")
async def handle_aggregate_confirm(ack, body, client, logger):
    """Team lead confirms aggregation and triggers mail draft."""
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle_confirm_action(
        body=body, client=client, logger=logger
    )


@slack_app.action("send_mail_confirm")
async def handle_send_mail_confirm(ack, body, client, logger):
    """Team lead confirms sending the aggregated report email."""
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle_send_mail_action(
        body=body, client=client, logger=logger
    )


def get_slack_app() -> AsyncApp:
    """Return the shared Slack Bolt app instance."""
    return slack_app
