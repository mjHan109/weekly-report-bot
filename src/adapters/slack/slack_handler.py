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


@slack_app.command("/메일설정")
async def cmd_mail_settings(ack, body, client, logger):
    await ack()
    from src.adapters.slack.handlers.mail_settings import MailSettingsHandler
    await MailSettingsHandler().handle(body=body, client=client, logger=logger)


@slack_app.command("/설정")
async def cmd_settings(ack, body, client, logger):
    """통합 설정 — /메일설정과 동일한 모달을 엽니다."""
    await ack()
    from src.adapters.slack.handlers.mail_settings import MailSettingsHandler
    await MailSettingsHandler().handle(body=body, client=client, logger=logger)


@slack_app.command("/보고현황")
async def cmd_report_status(ack, body, client, logger):
    """이번 주 보고 제출 현황 조회."""
    await ack()
    from src.adapters.slack.handlers.report_status import ReportStatusHandler
    await ReportStatusHandler().handle(body=body, client=client, logger=logger)



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


@slack_app.view("mail_settings_modal")
async def handle_mail_settings_modal(ack, body, view, logger):
    await ack()
    from src.adapters.slack.handlers.mail_settings import MailSettingsHandler
    await MailSettingsHandler().handle_modal_submit(body=body, view=view, logger=logger)


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
async def handle_dm_message(event, body, client, logger):
    """Route incoming DM messages to the conversational report flow."""
    # ── 중복 이벤트 방지 ──────────────────────────────────────────────────────
    from src.adapters.slack.event_deduplicator import is_duplicate_event
    event_id = body.get("event_id")
    if is_duplicate_event(event_id):
        logger.debug("Duplicate event dropped | event_id=%s", event_id)
        return

    channel_type = event.get("channel_type")
    subtype = event.get("subtype")
    user_id = event.get("user")
    dm_channel = event.get("channel", "")
    text = event.get("text", "")

    logger.info(
        "message event | event_id=%s channel_type=%s subtype=%s user=%s channel=%s text_len=%d",
        event_id, channel_type, subtype, user_id, dm_channel, len(text),
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


@slack_app.action("resume_draft_write")
async def action_resume_draft(ack, body, client, logger):
    """[이어쓰기] button — resume from saved DRAFT."""
    await ack()
    import json
    payload = json.loads(body["actions"][0]["value"])
    user_id = body["user"]["id"]
    dm_channel = body["channel"]["id"]
    from src.adapters.slack.handlers.dm_report_flow import resume_draft
    await resume_draft(
        user_id=user_id, dm_channel=dm_channel,
        channel_id=payload["channel_id"], is_late=payload["is_late"],
        client=client,
    )


@slack_app.action("quick_write_start")
async def action_quick_write_start(ack, body, client, logger):
    """[빠른 작성] / [새로 작성] button — start conversational flow."""
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


@slack_app.action("send_reminder_dms")
async def handle_send_reminder_dms(ack, body, client, logger):
    """Send DM reminders to unsubmitted reporters."""
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle_reminder_action(body=body, client=client, logger=logger)


@slack_app.action("status_aggregate_trigger")
async def handle_status_aggregate_trigger(ack, body, client, logger):
    """/보고현황 에서 [팀 보고 취합] 버튼 — /취합 흐름을 바로 시작."""
    await ack()
    user_id: str = body["user"]["id"]
    channel_id: str = body["actions"][0]["value"]
    fake_body = {"user_id": user_id, "channel_id": channel_id}
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle(body=fake_body, client=client, logger=logger)


@slack_app.action("aggregate_confirm")
async def handle_aggregate_confirm(ack, body, client, logger):
    """Team lead confirms aggregation — builds draft and posts preview."""
    await ack()
    from src.adapters.slack.handlers.aggregate_report import AggregateReportHandler
    await AggregateReportHandler().handle_confirm_action(
        body=body, client=client, logger=logger
    )


@slack_app.action("mail_draft_open")
async def handle_mail_draft_open(ack, body, client, logger):
    """Show email draft preview as an ephemeral message to the team lead."""
    await ack()
    draft_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    from src.services.acl.team_lead_service import require_team_lead_slack
    if not await require_team_lead_slack(user_id, channel_id, client):
        return

    from src.adapters.slack.draft_store import get_draft
    from src.adapters.slack.blocks.mail_draft_preview import build_mail_draft_preview
    draft = get_draft(draft_id)
    if not draft:
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="메일 초안을 찾을 수 없습니다. /취합 을 다시 실행해주세요."
        )
        return

    msg = build_mail_draft_preview(draft)
    await client.chat_postEphemeral(channel=channel_id, user=user_id, **msg)
    logger.info("mail_draft_open | draft=%s | user=%s", draft_id, user_id)


@slack_app.action("mail_draft_edit")
async def handle_mail_draft_edit(ack, body, client, logger):
    """Open edit modal for the email draft."""
    await ack()
    draft_id = body["actions"][0]["value"]
    trigger_id = body["trigger_id"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    from src.services.acl.team_lead_service import require_team_lead_slack
    if not await require_team_lead_slack(user_id, channel_id, client):
        return

    from src.adapters.slack.draft_store import get_draft
    from src.adapters.slack.blocks.mail_draft_modal import build_mail_draft_modal
    draft = get_draft(draft_id)
    if not draft:
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="메일 초안을 찾을 수 없습니다. /취합 을 다시 실행해주세요."
        )
        return

    # Try to load departments from org_users for quick-fill
    departments: list[str] = []
    try:
        from src.infra.db import _get_session_factory
        from src.domain.repositories.org_user_repo import OrgUserRepository
        factory = _get_session_factory()
        async with factory() as session:
            repo = OrgUserRepository(session)
            departments = await repo.list_departments()
    except Exception as e:
        logger.debug("Could not load departments: %s", e)

    await client.views_open(
        trigger_id=trigger_id,
        view=build_mail_draft_modal(draft, departments=departments or None),
    )
    logger.info("mail_draft_edit modal opened | draft=%s | depts=%d", draft_id, len(departments))


@slack_app.action("dept_select")
async def handle_dept_select(ack, body, client, logger):
    """User selected a department — fill To field with all dept emails."""
    await ack()
    selected_dept = body["actions"][0]["selected_option"]["value"]
    view_id = body["view"]["id"]
    draft_id = body["view"]["private_metadata"]

    from src.adapters.slack.draft_store import get_draft, update_draft
    draft = get_draft(draft_id)
    if not draft:
        return

    # Fetch department members from DB
    emails: list[str] = []
    try:
        from src.infra.db import _get_session_factory
        from src.domain.repositories.org_user_repo import OrgUserRepository
        factory = _get_session_factory()
        async with factory() as session:
            repo = OrgUserRepository(session)
            users = await repo.get_by_department(selected_dept)
            emails = [u.email for u in users if u.email]
    except Exception as e:
        logger.warning("dept_select: DB error: %s", e)

    if not emails:
        return

    mail_to = ", ".join(emails)
    update_draft(draft_id, mail_to=mail_to)
    draft = get_draft(draft_id)

    # Reload departments for the updated modal
    departments: list[str] = []
    try:
        from src.infra.db import _get_session_factory
        from src.domain.repositories.org_user_repo import OrgUserRepository
        factory = _get_session_factory()
        async with factory() as session:
            repo = OrgUserRepository(session)
            departments = await repo.list_departments()
    except Exception:
        pass

    from src.adapters.slack.blocks.mail_draft_modal import build_mail_draft_modal
    await client.views_update(
        view_id=view_id,
        view=build_mail_draft_modal(draft, departments=departments or None),
    )
    logger.info("dept_select: filled To with %d emails from dept=%s", len(emails), selected_dept)


@slack_app.view("mail_draft_edit_modal")
async def handle_mail_draft_edit_modal(ack, body, view, client, logger):
    """Save edited draft and re-post ephemeral preview."""
    await ack()
    draft_id = view["private_metadata"]
    values = view["state"]["values"]

    mail_to = values["mail_to"]["value"]["value"].strip()
    mail_cc = (values["mail_cc"]["value"]["value"] or "").strip()
    mail_subject = values["mail_subject"]["value"]["value"].strip()
    mail_body = values["mail_body"]["value"]["value"].strip()

    from src.adapters.slack.draft_store import get_draft, update_draft
    draft = get_draft(draft_id)
    if not draft:
        logger.warning("mail_draft_edit_modal: draft not found | draft=%s", draft_id)
        return

    update_draft(draft_id, mail_to=mail_to, mail_cc=mail_cc, mail_subject=mail_subject, mail_body=mail_body)
    draft = get_draft(draft_id)

    user_id = body["user"]["id"]
    channel_id = draft.channel_id

    from src.adapters.slack.blocks.mail_draft_preview import build_mail_draft_preview
    msg = build_mail_draft_preview(draft)
    await client.chat_postEphemeral(channel=channel_id, user=user_id, **msg)
    logger.info("mail_draft updated | draft=%s", draft_id)


@slack_app.action("mail_draft_send")
async def handle_mail_draft_send(ack, body, client, logger):
    """Send the email draft."""
    await ack()
    draft_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    # ── 팀장 권한 체크 ────────────────────────────────────────────────────────
    from src.services.acl.team_lead_service import require_team_lead_slack
    if not await require_team_lead_slack(user_id, channel_id, client):
        return

    from src.adapters.slack.draft_store import get_draft, delete_draft, update_draft
    draft = get_draft(draft_id)
    if not draft:
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="메일 초안을 찾을 수 없습니다. /취합 을 다시 실행해주세요."
        )
        return

    # ── Idempotency: 중복 클릭 방지 ──────────────────────────────────────────
    if draft.is_sending:
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="⏳ 이미 발송 중입니다. 잠시 기다려주세요."
        )
        return
    update_draft(draft_id, is_sending=True)

    if not draft.mail_to:
        update_draft(draft_id, is_sending=False)
        await client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="수신자 이메일 주소가 없습니다. ✏️ 수정 버튼으로 수신자를 입력해주세요."
        )
        return

    import asyncio

    to_list = [a.strip() for a in draft.mail_to.split(",") if a.strip()]
    cc_list = [a.strip() for a in (draft.mail_cc or "").split(",") if a.strip()]

    try:
        # ── 1. Resolve team lead AAD OID ─────────────────────────────────────
        from src.services.reports.report_service import ReportService
        oid = await ReportService().resolve_slack_to_aad(user_id)
        sent_via = "smtp"

        # ── 2. Try Graph API (Outlook) if a real AAD OID is available ────────
        if oid and oid != user_id:
            from src.services.mail.graph_client import GraphClient
            from src.services.mail.token_manager import TokenManager, TokenUnavailableError
            try:
                gc = GraphClient(TokenManager())
                loop = asyncio.get_event_loop()
                msg_obj = await loop.run_in_executor(
                    None,
                    lambda: gc.create_draft(
                        oid,
                        to=to_list,
                        cc=cc_list,
                        subject=draft.mail_subject,
                        body=draft.mail_body,
                    ),
                )
                await loop.run_in_executor(None, lambda: gc.send_draft(oid, msg_obj["id"]))
                sent_via = "graph"
                logger.info("Mail sent via Graph | oid=%s | draft=%s", oid, draft_id)
            except TokenUnavailableError:
                # Token not yet issued — guide user to /재인증 and abort
                update_draft(draft_id, is_sending=False)
                from src.adapters.slack.auth_notify import notify_token_expired
                await notify_token_expired(channel_id, user_id, client)
                return

        # ── 3. Fallback: Gmail SMTP (no Azure OID or Graph unavailable) ──────
        if sent_via == "smtp":
            from src.services.mail.smtp_service import GmailSmtpService
            await GmailSmtpService().send_weekly_report(
                subject=draft.mail_subject,
                body_text=draft.mail_body,
                to=draft.mail_to,
                cc=draft.mail_cc,
            )
            logger.info("Mail sent via SMTP | draft=%s | to=%s", draft_id, draft.mail_to)

        # ── AuditLog 기록 ────────────────────────────────────────────────────
        try:
            from src.infra.db import _get_session_factory
            from src.domain.repositories.audit_log_repo import AuditLogRepository
            factory = _get_session_factory()
            async with factory() as session:
                async with session.begin():
                    await AuditLogRepository(session).append(
                        event_type="mail.send",
                        actor_aad_id=oid or user_id,
                        channel_id=channel_id,
                        week_key=draft.report_week,
                        payload={
                            "draft_id": draft_id,
                            "to": draft.mail_to,
                            "cc": draft.mail_cc,
                            "subject": draft.mail_subject,
                            "via": sent_via,
                        },
                    )
        except Exception as audit_exc:
            logger.warning("AuditLog write failed (non-fatal): %s", audit_exc)

        delete_draft(draft_id)
        via_label = "Outlook" if sent_via == "graph" else "Gmail"
        await client.chat_postMessage(
            channel=draft.channel_id,
            text=f"✅ 주간 보고 메일이 발송되었습니다. ({via_label} / 수신: {draft.mail_to})",
        )
    except Exception as exc:
        update_draft(draft_id, is_sending=False)
        logger.error("Mail send failed | draft=%s | %s", draft_id, exc)

        from src.adapters.slack.auth_notify import (
            is_rate_limit_error,
            notify_rate_limited, notify_graph_error,
        )
        if is_rate_limit_error(exc):
            await notify_rate_limited(channel_id, user_id, client)
        else:
            await notify_graph_error(channel_id, user_id, client, detail=str(exc))


@slack_app.action("mail_draft_cancel")
async def handle_mail_draft_cancel(ack, body, client, logger):
    """Cancel and delete the email draft."""
    await ack()
    draft_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    from src.services.acl.team_lead_service import require_team_lead_slack
    if not await require_team_lead_slack(user_id, channel_id, client):
        return

    from src.adapters.slack.draft_store import delete_draft
    delete_draft(draft_id)
    await client.chat_postEphemeral(
        channel=channel_id, user=user_id, text="메일 발송이 취소되었습니다."
    )
    logger.info("mail_draft cancelled | draft=%s | user=%s", draft_id, user_id)


def get_slack_app() -> AsyncApp:
    """Return the shared Slack Bolt app instance."""
    return slack_app
