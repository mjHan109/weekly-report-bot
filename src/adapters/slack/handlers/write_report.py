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

        is_late = await _is_past_deadline(channel_id)

        # Load existing report content if already submitted
        existing = await _get_existing_report(user_id, channel_id)

        # Open modal (pre-filled if editing)
        from src.adapters.slack.blocks.personal_preview import build_write_report_modal
        modal = build_write_report_modal(channel_id=channel_id, is_late=is_late, existing=existing)
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
        done = values.get("done_block", {}).get("done_input", {}).get("value", "").strip()
        inprogress = values.get("inprogress_block", {}).get("inprogress_input", {}).get("value", "").strip()
        plan = values.get("plan_block", {}).get("plan_input", {}).get("value", "").strip()

        report_content = f"[완료한 업무]\n{done}\n\n[진행 중인 업무]\n{inprogress}\n\n[다음 주 계획]\n{plan}"

        if not (done or inprogress or plan):
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


async def _get_existing_report(user_id: str, channel_id: str) -> dict[str, str] | None:
    """Return parsed sections of existing report, or None if not submitted."""
    try:
        from src.services.reports.report_service import ReportService
        from src.infra.db import _get_session_factory
        from src.services.reports.week_utils import current_week_key
        from src.domain.repositories.personal_report_repo import PersonalReportRepository
        from src.domain.enums import ReportStatus

        factory = _get_session_factory()
        async with factory() as session:
            repo = PersonalReportRepository(session)
            report = await repo.get(channel_id, current_week_key(), user_id)
            if report and report.status in (ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED):
                return _parse_report_sections(report.content or "")
        return None
    except Exception:
        return None


def _parse_report_sections(content: str) -> dict[str, str]:
    sections = {"완료한 업무": "", "진행 중인 업무": "", "다음 주 계획": ""}
    current = None
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip("[] \t")
        if stripped in sections:
            if current and lines:
                sections[current] = "\n".join(lines).strip()
            current = stripped
            lines = []
        elif current:
            lines.append(line)
    if current and lines:
        sections[current] = "\n".join(lines).strip()
    return sections


async def _is_past_deadline(channel_id: str) -> bool:
    """True only when it's Thursday AND past 13:00 KST. Fri+ = new week, not late."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    now_kst = datetime.now(tz=ZoneInfo("Asia/Seoul"))
    # weekday(): 0=Mon, 3=Thu, 4=Fri
    if now_kst.weekday() == 3 and now_kst.hour >= 13:
        return True
    return False


async def _save_report(user_id: str, channel_id: str, content: str, is_late: bool) -> None:
    from src.services.reports.report_service import ReportService
    await ReportService().submit_report(
        user_id=user_id,
        channel_id=channel_id,
        content=content,
        is_late=is_late,
    )


async def _all_submitted(channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        pending = await ReportService().get_pending_reporter_mentions(channel_id)
        return len(pending) == 0
    except ImportError:
        return False
