"""
AggregateReportHandler — /취합 slash command. (팀장 전용)

Flow
----
  Team lead types /취합
    -> ACL check (must be team lead for this channel)
    -> Show aggregated preview message with "메일 발송" button

  Button action (action_id = "aggregate_confirm")
    -> Trigger LLM aggregation
    -> Post aggregate_preview Block Kit message
    -> Enable mail draft creation
"""

from __future__ import annotations

import logging


class AggregateReportHandler:

    async def handle(self, body: dict, client, logger) -> None:
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="팀장 전용 명령어입니다. `/팀장등록` 으로 팀장을 등록하세요.",
            )
            return

        pending_info = await _get_pending_reporters_with_slack_ids(channel_id)
        pending_aad_ids = [p["aad_id"] for p in pending_info]
        pending_slack_ids = [p["slack_user_id"] for p in pending_info if p.get("slack_user_id")]

        if pending_info:
            names = ", ".join(
                f"<@{p['slack_user_id']}>" if p.get("slack_user_id") else p["display_name"]
                for p in pending_info
            )
            reminder_note = (
                f"⏰ 미제출자 {len(pending_info)}명에게 DM 리마인드를 전송할 수 있습니다."
                if pending_slack_ids else
                "⚠️ 미제출자의 Slack 계정이 연동되지 않아 DM 전송이 불가합니다."
            )
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📋 *미제출자 목록*\n{names}\n\n{reminder_note}",
                        },
                    },
                    *(
                        [{
                            "type": "actions",
                            "elements": [{
                                "type": "button",
                                "action_id": "send_reminder_dms",
                                "text": {"type": "plain_text", "text": "📨 DM 리마인드 전송"},
                                "value": channel_id,
                                "style": "primary",
                            }],
                        }]
                        if pending_slack_ids else []
                    ),
                ],
                text=f"미제출자: {names}",
            )

        from src.adapters.slack.blocks.team_lead_pending import build_team_lead_pending_message
        msg = build_team_lead_pending_message(
            channel_id=channel_id,
            pending_user_ids=pending_aad_ids,
        )
        await client.chat_postEphemeral(channel=channel_id, user=user_id, **msg)
        logger.info("AggregateReportHandler: pending card shown | user=%s | channel=%s", user_id, channel_id)

    async def handle_reminder_action(self, body: dict, client, logger) -> None:
        """Send DM reminders to all unsubmitted reporters (action_id=send_reminder_dms)."""
        user_id: str = body["user"]["id"]
        channel_id: str = body["actions"][0]["value"]

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id, user=user_id, text="권한이 없습니다."
            )
            return

        from src.services.reports.report_service import ReportService
        sent = await ReportService().send_unsubmitted_reminders(channel_id, client)

        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=f"✅ 미제출자 {sent}명에게 DM 리마인드를 전송했습니다." if sent
                 else "⚠️ 전송할 미제출자가 없거나 Slack 계정이 연동되지 않았습니다.",
        )
        logger.info("Reminder DMs sent: count=%d channel=%s by=%s", sent, channel_id, user_id)

    async def handle_confirm_action(self, body: dict, client, logger) -> None:
        user_id: str = body["user"]["id"]
        channel_id: str = body["channel"]["id"]

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id, user=user_id, text="권한이 없습니다."
            )
            return

        try:
            aggregated_text = await _aggregate(channel_id, slack_client=client)
        except Exception as exc:
            from src.adapters.slack.auth_notify import (
                is_token_error, is_rate_limit_error,
                notify_token_expired, notify_rate_limited, notify_graph_error,
            )
            if is_token_error(exc):
                await notify_token_expired(channel_id, user_id, client)
            elif is_rate_limit_error(exc):
                await notify_rate_limited(channel_id, user_id, client)
            else:
                await notify_graph_error(channel_id, user_id, client, detail=str(exc))
            logger.error("Aggregation failed | channel=%s | %s", channel_id, exc)
            return

        from datetime import date
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        report_week = f"{iso_year}-W{iso_week:02d}"

        # Load per-channel mail settings
        from src.infra.db import _get_session_factory
        mail_settings = None
        try:
            factory = _get_session_factory()
            async with factory() as session:
                from src.domain.repositories.mail_settings_repo import MailSettingsRepository
                mail_settings = await MailSettingsRepository(session).get(channel_id)
        except Exception as e:
            logger.warning("handle_confirm_action: could not load mail settings: %s", e)

        team_name = (mail_settings.team_name if mail_settings else "") or "개발팀"
        sender_name = (mail_settings.sender_name if mail_settings else "") or ""
        greeting = (mail_settings.greeting if mail_settings else "") or ""
        closing = (mail_settings.closing if mail_settings else "") or ""
        default_to = (mail_settings.default_mail_to if mail_settings else "") or ""
        default_cc = (mail_settings.default_mail_cc if mail_settings else "") or ""

        from src.services.llm.aggregation_service import AggregationService
        email_body = AggregationService().format_for_email(
            aggregated_text,
            greeting=greeting,
            closing=closing,
            team_name=team_name,
            sender_name=sender_name,
        )
        # 메일 제목: 설정된 포맷 사용, 없으면 기본값
        if mail_settings:
            subject = mail_settings.render_subject(report_week)
        else:
            subject = f"[주간보고] {report_week} {team_name} 주간보고서"

        from src.adapters.slack.draft_store import create_draft
        draft = create_draft(
            channel_id=channel_id,
            report_week=report_week,
            mail_to=default_to,
            mail_cc=default_cc,
            mail_subject=subject,
            mail_body=email_body,
        )

        from src.adapters.slack.blocks.aggregate_preview import build_aggregate_preview_message
        msg = build_aggregate_preview_message(
            aggregated_text=aggregated_text,
            draft_id=draft.draft_id,
            report_week=report_week,
        )
        resp = await client.chat_postMessage(channel=channel_id, **msg)

        # Store message ts so we can update it later
        from src.adapters.slack.draft_store import update_draft
        update_draft(draft.draft_id, preview_channel=channel_id, preview_ts=resp["ts"])

        # ── AuditLog 기록 ─────────────────────────────────────────────────────
        try:
            from src.infra.db import _get_session_factory
            from src.domain.repositories.audit_log_repo import AuditLogRepository
            from src.services.reports.report_service import ReportService
            aad_id = await ReportService().resolve_slack_to_aad(user_id)
            factory = _get_session_factory()
            async with factory() as session:
                async with session.begin():
                    await AuditLogRepository(session).append(
                        event_type="team_report.aggregate",
                        actor_aad_id=aad_id,
                        channel_id=channel_id,
                        week_key=report_week,
                        payload={"draft_id": draft.draft_id},
                    )
        except Exception as audit_exc:
            logger.warning("AuditLog write failed (non-fatal): %s", audit_exc)

        logger.info(
            "AggregateReportHandler: aggregate posted | channel=%s | draft=%s",
            channel_id, draft.draft_id,
        )


async def _is_team_lead(user_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        svc = ReportService()
        aad_id = await svc.resolve_slack_to_aad(user_id)
        is_lead = await svc.is_team_lead(aad_id, channel_id)
        # Fallback: Slack user_id may have been stored directly before mapping was implemented
        if not is_lead and aad_id != user_id:
            is_lead = await svc.is_team_lead(user_id, channel_id)
        return is_lead
    except Exception:
        logging.getLogger(__name__).warning("_is_team_lead check failed — denying by default")
        return False


async def _get_pending_reporters_with_slack_ids(channel_id: str) -> list[dict]:
    """Return pending reporters with display_name and slack_user_id."""
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_unsubmitted_with_slack_ids(channel_id)
    except Exception:
        return []


async def _aggregate(channel_id: str, slack_client=None) -> str:
    from src.services.llm.aggregation_service import AggregationService
    return await AggregationService().aggregate_weekly_reports(
        channel_id, slack_client=slack_client
    )
