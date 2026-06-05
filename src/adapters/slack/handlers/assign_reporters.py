"""
AssignReportersHandler — /보고대상 slash command. (팀장 전용)

Flow
----
  Team lead types /보고대상
    -> ACL check
    -> Open assign_reporters_modal (multi-user select)

  Modal submit (callback_id = "assign_reporters_modal")
    -> Persist reporter list for this channel
    -> Post confirmation
"""

from __future__ import annotations

import logging


class AssignReportersHandler:

    async def handle(self, body: dict, client, logger) -> None:
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]

        is_lead = await _is_team_lead(user_id, channel_id)
        if not is_lead:
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="팀장 전용 명령어입니다.",
            )
            return

        from src.adapters.slack.blocks.personal_preview import build_assign_reporters_modal
        modal = build_assign_reporters_modal(channel_id=channel_id)
        await client.views_open(trigger_id=body["trigger_id"], view=modal)
        logger.info("AssignReportersHandler: modal opened | user=%s | channel=%s", user_id, channel_id)

    async def handle_modal_submit(self, body: dict, client, view: dict, logger) -> None:
        user_id: str = body["user"]["id"]
        channel_id: str = view.get("private_metadata", "")

        values = view["state"]["values"]
        selected_users: list[str] = (
            values.get("reporters_block", {})
            .get("reporters_select", {})
            .get("selected_users", [])
        )

        if not selected_users:
            logger.warning("AssignReportersHandler: no users selected by %s", user_id)
            return

        # Fetch display names from Slack
        display_names: dict[str, str] = {}
        for uid in selected_users:
            try:
                resp = await client.users_info(user=uid)
                profile = resp["user"]["profile"]
                display_names[uid] = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or uid
                )
            except Exception:
                display_names[uid] = uid

        await _save_reporters(channel_id, selected_users, display_names)

        names = " ".join(f"<@{uid}>" for uid in selected_users)
        await client.chat_postMessage(
            channel=channel_id,
            text=f"보고 대상자가 설정되었습니다: {names}",
        )
        logger.info(
            "AssignReportersHandler: reporters saved | channel=%s | count=%d",
            channel_id, len(selected_users),
        )


async def _is_team_lead(user_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_team_lead(user_id, channel_id)
    except ImportError:
        logging.getLogger(__name__).warning("ReportService stub — returns True")
        return True


async def _save_reporters(channel_id: str, user_ids: list[str], display_names: dict[str, str] | None = None) -> None:
    from src.services.reports.report_service import ReportService
    await ReportService().set_designated_reporters(channel_id, user_ids, display_names or {})
