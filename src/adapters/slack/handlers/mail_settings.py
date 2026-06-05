"""MailSettingsHandler — /메일설정 slash command."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db import _get_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


class MailSettingsHandler:

    async def handle(self, body: dict, client, logger) -> None:
        """Open the mail settings modal for this channel."""
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]
        trigger_id: str = body["trigger_id"]

        # ACL: team leads only
        from src.adapters.slack.handlers.aggregate_report import _is_team_lead
        if not await _is_team_lead(user_id, channel_id):
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="팀장 전용 명령어입니다.",
            )
            return

        async with _session() as session:
            from src.domain.repositories.mail_settings_repo import MailSettingsRepository
            repo = MailSettingsRepository(session)
            settings = await repo.get_or_default(channel_id)

        from src.adapters.slack.blocks.mail_settings_modal import build_mail_settings_modal
        await client.views_open(
            trigger_id=trigger_id,
            view=build_mail_settings_modal(settings),
        )
        logger.info("MailSettingsHandler: modal opened | channel=%s user=%s", channel_id, user_id)

    async def handle_modal_submit(self, body: dict, view: dict, logger) -> None:
        """Save submitted settings (all fields from build_mail_settings_modal)."""
        channel_id: str = view["private_metadata"]
        values = view["state"]["values"]

        def _val(block: str) -> str:
            block_data = values.get(block, {})
            action = block_data.get("value", {})
            return (action.get("value") or "").strip()

        def _select_val(block: str) -> str:
            block_data = values.get(block, {})
            action = block_data.get("value", {})
            selected = action.get("selected_option") or {}
            return selected.get("value", "")

        def _checkbox_checked(block: str, option_value: str) -> bool:
            block_data = values.get(block, {})
            action = block_data.get("value", {})
            selected = action.get("selected_options") or []
            return any(o.get("value") == option_value for o in selected)

        async with _session() as session:
            from src.domain.repositories.mail_settings_repo import MailSettingsRepository
            repo = MailSettingsRepository(session)
            s = await repo.get_or_default(channel_id)
            s.channel_id = channel_id

            # Team info
            s.team_name = _val("team_name") or "개발팀"
            s.sender_name = _val("sender_name")

            # Schedule
            weekday_str = _select_val("deadline_weekday")
            try:
                s.deadline_weekday = int(weekday_str)
            except (ValueError, TypeError):
                s.deadline_weekday = 3  # default: 목요일
            hour_str = _val("deadline_hour")
            try:
                hour = int(hour_str)
                s.deadline_hour = max(0, min(23, hour))
            except (ValueError, TypeError):
                s.deadline_hour = 13
            s.reminder_hours = _val("reminder_hours")

            # Report template
            s.report_template = _val("report_template")

            # Mail template
            s.mail_subject_format = _val("mail_subject_format") or s.mail_subject_format
            s.greeting = _val("greeting")
            s.closing = _val("closing")

            # Recipients
            s.default_mail_to = _val("default_mail_to")
            s.default_mail_cc = _val("default_mail_cc")
            s.auto_cc_team_lead = _checkbox_checked("auto_cc_team_lead", "yes")

            await repo.save(s)

        logger.info("MailSettingsHandler: settings saved | channel=%s", channel_id)
