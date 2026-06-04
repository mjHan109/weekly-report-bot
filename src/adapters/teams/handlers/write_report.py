"""
WriteReportHandler — "이번 주 보고 작성" command.

ACL rules
---------
1. The invoking user MUST be on the designated-reporter list for this channel.
2. Identity is read from activity.from_.aad_object_id (set by bot_handler).
3. If the submission deadline (Thu 13:00) has already passed, the user is
   allowed to self-submit late (late flag is set in the Task Module hidden
   field — no proxy submit by team lead is permitted per ADR-006).

Flow
----
  User types "이번 주 보고 작성"
    -> ACL check
    -> Return task/continue with report form Task Module payload
       (the actual fetch payload is built by ReportFormModule)
"""

from __future__ import annotations

import logging
from typing import Optional

from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes

logger = logging.getLogger(__name__)


class WriteReportHandler:
    """Handles the '이번 주 보고 작성' command."""

    async def handle(self, turn_context: TurnContext) -> None:
        aad_id: Optional[str] = _get_aad_id(turn_context)
        channel_id: Optional[str] = _get_channel_id(turn_context)

        if not aad_id or not channel_id:
            await _reply(turn_context, "사용자 또는 채널 정보를 확인할 수 없습니다.")
            return

        # ACL check: must be a designated reporter for this channel
        is_designated = await _is_designated_reporter(aad_id, channel_id)
        if not is_designated:
            await _reply(
                turn_context,
                "보고 대상자가 아닙니다. 팀장에게 '보고 대상 지정'을 요청하세요.",
            )
            return

        # Check whether the deadline has already passed (late submit)
        is_late = await _is_past_deadline(channel_id)

        # Check if already submitted this week
        already_submitted = await _already_submitted_this_week(aad_id, channel_id)
        if already_submitted:
            await _reply(turn_context, "이번 주 보고를 이미 제출하셨습니다.")
            return

        logger.info(
            "WriteReportHandler: opening report form | aad_id=%s | channel=%s | late=%s",
            aad_id,
            channel_id,
            is_late,
        )

        # Return a task/continue invoke response to open the Task Module.
        # The actual card payload is built by ReportFormModule.build_fetch_payload()
        # which is called from bot_handler._handle_task_fetch() when Teams fires
        # the task/fetch invoke. Here we just trigger opening via a hero card button.
        from src.adapters.teams.task_module.report_form import ReportFormModule

        module = ReportFormModule()
        task_payload = await module.build_fetch_payload(
            turn_context=turn_context,
            aad_id=aad_id,
            channel_id=channel_id,
        )

        # Send as an invoke-compatible response wrapped in a message with
        # a task/fetch button so Teams opens the Task Module iframe.
        from botbuilder.schema import (
            Attachment,
            CardAction,
            HeroCard,
            ActionTypes,
        )

        task_info_value = {
            "taskModuleId": "reportForm",
            "channelId": channel_id,
            "isLate": is_late,
        }

        button = CardAction(
            type=ActionTypes.invoke,
            title="보고서 작성하기",
            value={
                "type": "task/fetch",
                "data": task_info_value,
            },
        )
        card = HeroCard(
            title="이번 주 보고 작성",
            text="아래 버튼을 눌러 보고서를 작성하세요." + (" (지각 제출)" if is_late else ""),
            buttons=[button],
        )
        attachment = Attachment(
            content_type="application/vnd.microsoft.card.hero",
            content=card.serialize(),
        )
        reply = Activity(
            type=ActivityTypes.message,
            attachments=[attachment],
        )
        await turn_context.send_activity(reply)


# ---------------------------------------------------------------------------
# Private helpers — these will delegate to service layer stubs
# ---------------------------------------------------------------------------

def _get_aad_id(turn_context: TurnContext) -> Optional[str]:
    from_account = getattr(turn_context.activity, "from_", None)
    if from_account is None:
        return None
    return getattr(from_account, "aad_object_id", None)


def _get_channel_id(turn_context: TurnContext) -> Optional[str]:
    conversation = getattr(turn_context.activity, "conversation", None)
    if conversation is None:
        return None
    return getattr(conversation, "id", None)


async def _is_designated_reporter(aad_id: str, channel_id: str) -> bool:
    """
    Delegate to the report service to check the designated reporter list.

    Stub: always returns True until ReportService is wired.
    Replace with: from src.services.reports.report_service import ReportService
    """
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_designated_reporter(aad_id, channel_id)
    except ImportError:
        logger.warning("ReportService not yet available — ACL stub returns True")
        return True


async def _is_past_deadline(channel_id: str) -> bool:
    """
    Check whether Thu 13:00 deadline has passed for the current week.

    Stub: returns False until DeadlineService is wired.
    """
    try:
        from src.services.reports.deadline_service import DeadlineService
        return await DeadlineService().is_past_deadline(channel_id)
    except ImportError:
        return False


async def _already_submitted_this_week(aad_id: str, channel_id: str) -> bool:
    """Check whether this user already submitted a report this week."""
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().has_submitted_this_week(aad_id, channel_id)
    except ImportError:
        return False


async def _reply(turn_context: TurnContext, text: str) -> None:
    await turn_context.send_activity(
        Activity(type=ActivityTypes.message, text=text)
    )
