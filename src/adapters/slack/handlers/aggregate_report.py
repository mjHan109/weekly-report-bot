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
        aggregated_text = await _aggregate(channel_id)

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


async def _aggregate(channel_id: str) -> str:
    try:
        from src.services.llm.aggregation_service import AggregationService
        return await AggregationService().aggregate_weekly_reports(channel_id)
    except ImportError:
        return "*(집계 서비스 준비 중입니다)*"
