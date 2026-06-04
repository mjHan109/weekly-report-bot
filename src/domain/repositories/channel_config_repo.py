"""ChannelConfigRepository — CRUD for ChannelConfig + ChannelReportTarget."""

import logging
from typing import Sequence

from sqlalchemy import select

from src.domain.models.channel_config import ChannelConfig
from src.domain.models.channel_report_target import ChannelReportTarget
from src.domain.repositories.base import ChannelScopedRepository

logger = logging.getLogger(__name__)


class ChannelConfigRepository(ChannelScopedRepository[ChannelConfig]):
    """Manages channel configuration and report-target membership."""

    # ── ChannelConfig ─────────────────────────────────────────────────────────

    async def get_by_channel_id(self, channel_id: str) -> ChannelConfig | None:
        """Fetch ChannelConfig by primary key."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(ChannelConfig).where(ChannelConfig.channel_id == cid)
        )
        return result.scalar_one_or_none()

    async def get_active_configs(self) -> Sequence[ChannelConfig]:
        """Return all active channel configurations."""
        result = await self._session.execute(
            select(ChannelConfig).where(ChannelConfig.is_active.is_(True))
        )
        return result.scalars().all()

    async def upsert(self, config: ChannelConfig) -> ChannelConfig:
        """Insert or update a ChannelConfig row."""
        self._require_channel_id(config.channel_id)
        self._session.add(config)
        await self._flush()
        await self._refresh(config)
        logger.info("Upserted ChannelConfig for channel_id=%r", config.channel_id)
        return config

    async def deactivate(self, channel_id: str) -> bool:
        """Soft-delete: set is_active=False.  Returns True if row existed."""
        cid = self._require_channel_id(channel_id)
        config = await self.get_by_channel_id(cid)
        if config is None:
            return False
        config.is_active = False
        await self._flush()
        return True

    # ── ChannelReportTarget ───────────────────────────────────────────────────

    async def get_active_targets(
        self, channel_id: str
    ) -> Sequence[ChannelReportTarget]:
        """Return all active report targets for a channel."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(ChannelReportTarget).where(
                ChannelReportTarget.channel_id == cid,
                ChannelReportTarget.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def get_target(
        self, channel_id: str, aad_object_id: str
    ) -> ChannelReportTarget | None:
        """Fetch a specific target by channel + AAD ID."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(ChannelReportTarget).where(
                ChannelReportTarget.channel_id == cid,
                ChannelReportTarget.aad_object_id == aad_object_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_target(self, target: ChannelReportTarget) -> ChannelReportTarget:
        """Add a new report target to a channel."""
        self._require_channel_id(target.channel_id)
        self._session.add(target)
        await self._flush()
        await self._refresh(target)
        return target

    async def remove_target(self, channel_id: str, aad_object_id: str) -> bool:
        """Soft-delete a target.  Returns True if the target was found."""
        target = await self.get_target(channel_id, aad_object_id)
        if target is None:
            return False
        target.is_active = False
        await self._flush()
        return True
