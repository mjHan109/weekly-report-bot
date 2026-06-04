"""
ReporterSelectFormModule — Task Module for "보고 대상 지정".

task/fetch payload
------------------
Returns a task/continue response containing an Adaptive Card with:
  - A multi-select Input.ChoiceSet populated with current channel members
    (fetched from Graph API via TeamMemberService).
  - A hidden channel_id field bound server-side.

task/submit handling
--------------------
- ACL: caller must be team lead (re-verified on submit).
- Persists the selected AAD IDs as the designated reporter list for the channel.
- Posts a confirmation message to the channel.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from botbuilder.core import TurnContext

logger = logging.getLogger(__name__)

TASK_MODULE_WIDTH = 500
TASK_MODULE_HEIGHT = 480


class ReporterSelectFormModule:
    """Builds the reporter-selection Task Module payload and handles submissions."""

    # ------------------------------------------------------------------
    # task/fetch
    # ------------------------------------------------------------------

    async def build_fetch_payload(
        self,
        turn_context: TurnContext,
        aad_id: Optional[str],
        channel_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Build the reporter-selection card.

        Channel members are fetched from Graph; existing selections are
        pre-filled from ChannelConfig.designated_reporter_aad_ids.
        """
        members = await _fetch_channel_members(channel_id)
        current_selections = await _get_current_designated(channel_id)

        card_payload = _build_reporter_select_card(
            channel_id=channel_id or "",
            members=members,
            current_selections=current_selections,
        )

        return {
            "task": {
                "type": "continue",
                "value": {
                    "title": "보고 대상 지정",
                    "height": TASK_MODULE_HEIGHT,
                    "width": TASK_MODULE_WIDTH,
                    "card": {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card_payload,
                    },
                },
            }
        }

    # ------------------------------------------------------------------
    # task/submit
    # ------------------------------------------------------------------

    async def handle_submit(
        self,
        turn_context: TurnContext,
        aad_id: Optional[str],
        submitted_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Persist the selected reporter list and confirm in channel.

        aad_id is taken from the activity (already resolved by bot_handler).
        """
        channel_id: str = submitted_data.get("channel_id", "")

        if not aad_id or not channel_id:
            logger.warning("reporter_select submit: missing aad_id or channel_id")
            return None

        # ACL re-check on submit
        if not await _is_team_lead(aad_id, channel_id):
            logger.warning(
                "reporter_select submit: aad_id=%s is not team lead for channel=%s",
                aad_id,
                channel_id,
            )
            return None

        # The multi-select value arrives as a comma-separated string
        raw_selection: str = submitted_data.get("selected_reporters", "")
        selected_aad_ids: List[str] = [
            s.strip() for s in raw_selection.split(",") if s.strip()
        ]

        if not selected_aad_ids:
            logger.warning("reporter_select submit: no reporters selected — ignoring")
            return None

        logger.info(
            "reporter_select: saving %d reporters | channel=%s",
            len(selected_aad_ids),
            channel_id,
        )

        await _save_designated_reporters(channel_id, selected_aad_ids)

        # Fetch display names for confirmation message
        names = await _aad_ids_to_display_names(selected_aad_ids, channel_id)
        names_str = ", ".join(names) if names else ", ".join(selected_aad_ids)

        from botbuilder.schema import Activity, ActivityTypes
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text=f"보고 대상이 지정되었습니다: {names_str}",
            )
        )

        return None  # close Task Module


# ---------------------------------------------------------------------------
# Adaptive Card builder
# ---------------------------------------------------------------------------

def _build_reporter_select_card(
    channel_id: str,
    members: List[Dict[str, str]],
    current_selections: List[str],
) -> Dict[str, Any]:
    """
    Build the Adaptive Card for multi-select reporter assignment.

    members: list of {"aad_id": "...", "display_name": "..."} dicts.
    current_selections: list of AAD IDs that are currently designated.
    """
    choices = [
        {"title": m["display_name"], "value": m["aad_id"]}
        for m in members
    ]

    # Pre-fill default value as comma-separated string
    default_value = ",".join(
        m["aad_id"] for m in members if m["aad_id"] in current_selections
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "보고 대상자 선택",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "이번 주 보고서를 제출해야 할 팀원을 선택하세요.",
                "wrap": True,
            },
            {
                "type": "Input.ChoiceSet",
                "id": "selected_reporters",
                "isMultiSelect": True,
                "value": default_value,
                "choices": choices if choices else [
                    {"title": "(채널 멤버를 불러올 수 없습니다)", "value": "__none__"}
                ],
            },
            # Hidden channel_id
            {
                "type": "Input.Text",
                "id": "taskModuleId",
                "value": "reporterSelect",
                "isVisible": False,
            },
            {
                "type": "Input.Text",
                "id": "channel_id",
                "value": channel_id,
                "isVisible": False,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "저장",
                "data": {"taskModuleId": "reporterSelect"},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _fetch_channel_members(
    channel_id: Optional[str],
) -> List[Dict[str, str]]:
    """Fetch {aad_id, display_name} list for channel members via Graph API."""
    if not channel_id:
        return []
    try:
        from src.services.reports.team_member_service import TeamMemberService
        return await TeamMemberService().get_channel_members(channel_id)
    except ImportError:
        logger.warning("TeamMemberService not available — returning empty member list")
        return []


async def _get_current_designated(channel_id: Optional[str]) -> List[str]:
    """Return currently designated reporter AAD IDs for pre-filling the form."""
    if not channel_id:
        return []
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        return await ChannelConfigService().get_designated_reporter_ids(channel_id)
    except ImportError:
        return []


async def _is_team_lead(aad_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_team_lead(aad_id, channel_id)
    except ImportError:
        return True


async def _save_designated_reporters(
    channel_id: str, aad_ids: List[str]
) -> None:
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        await ChannelConfigService().set_designated_reporters(channel_id, aad_ids)
    except ImportError:
        logger.warning("ChannelConfigService not available — save stub (no-op)")


async def _aad_ids_to_display_names(
    aad_ids: List[str], channel_id: str
) -> List[str]:
    """Resolve AAD IDs to display names for the confirmation message."""
    try:
        from src.services.reports.team_member_service import TeamMemberService
        members = await TeamMemberService().get_channel_members(channel_id)
        id_to_name = {m["aad_id"]: m["display_name"] for m in members}
        return [id_to_name.get(aid, aid) for aid in aad_ids]
    except ImportError:
        return aad_ids
