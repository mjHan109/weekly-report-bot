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

        pending = await _get_pending_reporters(channel_id)
        if pending:
            names = ", ".join(f"<@{uid}>" for uid in pending)
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"아직 미제출자가 있습니다: {names}\n미제출자 보고 대기 후 취합하거나, 직접 취합을 진행하세요.",
            )

        from src.adapters.slack.blocks.team_lead_pending import build_team_lead_pending_message
        msg = build_team_lead_pending_message(
            channel_id=channel_id,
            pending_user_ids=pending,
        )
        await client.chat_postEphemeral(channel=channel_id, user=user_id, **msg)
        logger.info("AggregateReportHandler: pending card shown | user=%s | channel=%s", user_id, channel_id)

    async def handle_confirm_action(self, body: dict, client, logger) -> None:
        user_id: str = body["user"]["id"]
        channel_id: str = body["channel"]["id"]

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id, user=user_id, text="권한이 없습니다."
            )
            return

        # Run LLM aggregation
        aggregated_text = await _aggregate(channel_id, slack_client=client)

        from src.adapters.slack.blocks.aggregate_preview import build_aggregate_preview_message
        from datetime import date
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        report_week = f"{iso_year}-W{iso_week:02d}"

        msg = build_aggregate_preview_message(
            aggregated_text=aggregated_text,
            channel_id=channel_id,
            report_week=report_week,
        )
        await client.chat_postMessage(channel=channel_id, **msg)
        logger.info("AggregateReportHandler: aggregate posted | channel=%s", channel_id)


    async def handle_send_mail_action(self, body: dict, client, logger) -> None:
        """Send the aggregated weekly report email after team lead confirms."""
        user_id: str = body["user"]["id"]
        channel_id: str = body["channel"]["id"]
        value: str = body["actions"][0].get("value", "|")
        channel_id_from_value, report_week = (value.split("|") + [""])[:2]
        channel_id = channel_id_from_value or channel_id

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id, user=user_id, text="권한이 없습니다."
            )
            return

        # Get aggregated content
        aggregated_text = await _aggregate(channel_id, slack_client=client)

        from src.services.llm.aggregation_service import AggregationService
        email_body = AggregationService().format_for_email(aggregated_text)

        # Build subject
        subject = f"[주간 보고] {report_week} 팀 주간 보고서"

        # Send email
        try:
            from src.services.mail.smtp_service import GmailSmtpService
            await GmailSmtpService().send_weekly_report(
                subject=subject,
                body_text=email_body,
            )
            await client.chat_postMessage(
                channel=channel_id,
                text=f"✅ 주간 보고 메일이 발송되었습니다. (`{report_week}`)",
            )
            logger.info("Mail sent | channel=%s | week=%s", channel_id, report_week)
        except Exception as exc:
            logger.error("Mail send failed: %s", exc)
            await client.chat_postMessage(
                channel=channel_id,
                text=f"❌ 메일 발송 실패: {exc}",
            )


async def _is_team_lead(user_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_team_lead(user_id, channel_id)
    except ImportError:
        logging.getLogger(__name__).warning("ReportService stub — returns True for team lead")
        return True


async def _get_pending_reporters(channel_id: str) -> list[str]:
    try:
        from src.services.reports.report_service import ReportService
        items = await ReportService().get_pending_reporter_mentions(channel_id)
        return [item["aad_id"] for item in items]
    except ImportError:
        return []


async def _aggregate(channel_id: str, slack_client=None) -> str:
    from src.services.llm.aggregation_service import AggregationService
    return await AggregationService().aggregate_weekly_reports(
        channel_id, slack_client=slack_client
    )
