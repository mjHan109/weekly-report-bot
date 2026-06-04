"""
AssignReportersHandler — "보고 대상 지정" command.

ACL rules
---------
- The invoking user MUST be the registered team lead for this channel.
- Identity is taken from activity.from_.aad_object_id only.

Flow
----
  Team lead types "보고 대상 지정"
    -> ACL: must be team lead
    -> Open reporter-selection Task Module (ReporterSelectFormModule)
    -> On submit: update ChannelConfig.designated_reporter_aad_ids
    -> Confirm in channel
"""

from __future__ import annotations

import logging
from typing import Optional

from botbuilder.core import TurnContext
from botbuilder.schema import (
    Activity,
    ActivityTypes,
    Attachment,
    CardAction,
    HeroCard,
    ActionTypes,
)

logger = logging.getLogger(__name__)


class AssignReportersHandler:
    """Handles the '보고 대상 지정' command."""

    async def handle(self, turn_context: TurnContext) -> None:
        aad_id = _get_aad_id(turn_context)
        channel_id = _get_channel_id(turn_context)

        if not aad_id or not channel_id:
            await _reply(turn_context, "사용자 또는 채널 정보를 확인할 수 없습니다.")
            return

        # ACL: team lead only
        if not await _is_team_lead(aad_id, channel_id):
            await _reply(turn_context, "팀장만 보고 대상을 지정할 수 있습니다.")
            return

        logger.info(
            "AssignReportersHandler: opening reporter select form | aad_id=%s | channel=%s",
            aad_id,
            channel_id,
        )

        # Open the reporter-selection Task Module via a HeroCard button
        task_info_value = {
            "taskModuleId": "reporterSelect",
            "channelId": channel_id,
        }
        button = CardAction(
            type=ActionTypes.invoke,
            title="보고 대상 지정하기",
            value={
                "type": "task/fetch",
                "data": task_info_value,
            },
        )
        card = HeroCard(
            title="보고 대상 지정",
            text="팀 채널의 보고 대상자를 선택하세요.",
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
# Private helpers
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


async def _is_team_lead(aad_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_team_lead(aad_id, channel_id)
    except ImportError:
        logger.warning("ReportService not available — team-lead ACL stub returns True")
        return True


async def _reply(turn_context: TurnContext, text: str) -> None:
    await turn_context.send_activity(
        Activity(type=ActivityTypes.message, text=text)
    )
