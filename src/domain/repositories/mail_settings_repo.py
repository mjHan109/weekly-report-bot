"""MailSettingsRepository — CRUD for per-channel email settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.mail_settings import MailSettings


class MailSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: str) -> MailSettings | None:
        result = await self._session.execute(
            select(MailSettings).where(MailSettings.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_or_default(self, channel_id: str) -> MailSettings:
        """Return existing settings or an unsaved default instance."""
        existing = await self.get(channel_id)
        if existing:
            return existing
        return MailSettings(channel_id=channel_id)

    async def save(self, settings: MailSettings) -> MailSettings:
        """Insert or update (merge) the settings record."""
        merged = await self._session.merge(settings)
        await self._session.flush()
        return merged
