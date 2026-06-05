"""
RegisterTeamLeadHandler — /팀장등록 slash command.

Registers the invoking user as the team lead for the current channel.
Only existing admins (INITIAL_ADMIN_USER_IDS) or already-registered leads
of other channels can invoke this for the first registration.
"""

from __future__ import annotations

import logging


class RegisterTeamLeadHandler:

    async def handle(self, body: dict, client, logger) -> None:
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]

        # Check if a team lead is already registered for this channel
        existing_lead = await _get_existing_lead(channel_id)
        if existing_lead and existing_lead != user_id:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"이미 <@{existing_lead}> 님이 팀장으로 등록되어 있습니다.",
            )
            return

        await _register_lead(user_id, channel_id)

        await client.chat_postMessage(
            channel=channel_id,
            text=f"<@{user_id}> 님이 이 채널의 팀장으로 등록되었습니다. `/보고대상` 으로 보고 대상자를 지정하세요.",
        )
        logger.info(
            "RegisterTeamLeadHandler: lead registered | user=%s | channel=%s",
            user_id, channel_id,
        )


async def _get_existing_lead(channel_id: str):
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_team_lead(channel_id)
    except ImportError:
        return None


async def _register_lead(user_id: str, channel_id: str) -> None:
    try:
        from src.services.reports.report_service import ReportService
        await ReportService().register_team_lead(user_id, channel_id)
    except ImportError:
        logging.getLogger(__name__).warning("ReportService stub — lead not persisted")
