"""
WriteReportHandler — /주간보고 slash command.

Flow
----
  User types /주간보고
    -> ACL check (must be designated reporter for this channel)
    -> If already submitted this week → ephemeral error message
    -> Open write_report_modal (Slack Modal / views.open)

  Modal submit (callback_id = "write_report_modal")
    -> Save personal report to DB
    -> Post confirmation in channel
    -> If all reporters submitted → notify team lead
"""

from __future__ import annotations

import logging
from typing import Optional


class WriteReportHandler:
    """Handles /주간보고 command and its modal submission."""

    async def handle(self, body: dict, client, logger) -> None:
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]

        # ACL check
        is_designated = await _is_designated_reporter(user_id, channel_id)
        if not is_designated:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="보고 대상자가 아닙니다. 팀장에게 `/보고대상` 설정을 요청하세요.",
            )
            return

        # Duplicate submission check
        already_submitted = await _already_submitted_this_week(user_id, channel_id)
        if already_submitted:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="이번 주 보고를 이미 제출하셨습니다.",
            )
            return

        is_late = await _is_past_deadline(channel_id)

        # Open modal
        from src.adapters.slack.blocks.personal_preview import build_write_report_modal
        modal = build_write_report_modal(channel_id=channel_id, is_late=is_late)
        await client.views_open(trigger_id=body["trigger_id"], view=modal)

        logger.info(
            "WriteReportHandler: modal opened | user=%s | channel=%s | late=%s",
            user_id, channel_id, is_late,
        )

    async def handle_modal_submit(self, body: dict, client, view: dict, logger) -> None:
        user_id: str = body["user"]["id"]
        metadata = view.get("private_metadata", "")
        channel_id, is_late_str = (metadata.split("|") + ["false"])[:2]
        is_late = is_late_str == "true"

        values = view["state"]["values"]
        report_content = (
            values.get("report_block", {})
            .get("report_input", {})
            .get("value", "")
        )

        if not report_content.strip():
            logger.warning("WriteReportHandler: empty report content from user=%s", user_id)
            return

        # Persist to DB
        await _save_report(user_id, channel_id, report_content, is_late)

        # Post confirmation to channel
        from src.adapters.slack.blocks.personal_preview import build_submission_confirmation
        msg = build_submission_confirmation(user_id=user_id, is_late=is_late)
        await client.chat_postMessage(channel=channel_id, **msg)

        # Check if all submitted → notify team lead
        all_done = await _all_submitted(channel_id)
        if all_done:
            from src.adapters.slack.blocks.team_lead_all_submitted import build_all_submitted_message
            lead_msg = build_all_submitted_message(channel_id=channel_id)
            await client.chat_postMessage(channel=channel_id, **lead_msg)

        logger.info(
            "WriteReportHandler: report saved | user=%s | channel=%s | all_done=%s",
            user_id, channel_id, all_done,
        )


# ---------------------------------------------------------------------------
# Private helpers — delegate to service layer
# ---------------------------------------------------------------------------

async def _is_designated_reporter(user_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_designated_reporter(user_id, channel_id)
    except ImportError:
        logging.getLogger(__name__).warning("ReportService stub — returns True")
        return True


async def _already_submitted_this_week(user_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().has_submitted_this_week(user_id, channel_id)
    except ImportError:
        return False


async def _is_past_deadline(channel_id: str) -> bool:
    try:
        from src.services.reports.deadline_service import DeadlineService
        return await DeadlineService().is_past_deadline(channel_id)
    except ImportError:
        return False


async def _save_report(user_id: str, channel_id: str, content: str, is_late: bool) -> None:
    try:
        from src.services.reports.submission_service import SubmissionService
        await SubmissionService().submit_report(
            user_id=user_id,
            channel_id=channel_id,
            content=content,
            is_late=is_late,
        )
    except ImportError:
        logging.getLogger(__name__).warning("SubmissionService stub — report not persisted")


async def _all_submitted(channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        pending = await ReportService().get_pending_reporter_mentions(channel_id)
        return len(pending) == 0
    except ImportError:
        return False
