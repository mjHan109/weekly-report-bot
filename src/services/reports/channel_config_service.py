"""ChannelConfigService — Teams channel configuration & conversation state.

Responsibilities
----------------
- Team lead registration / lookup for a Teams channel.
- ConversationReference persistence (required for proactive messaging).
- Lead card activity_id persistence (for in-place Adaptive Card updates).

Storage
-------
All mutable state is stored in ChannelConfig.extra_config (JSON blob) so no
additional DB columns are needed.  The service uses the existing
ChannelConfigRepository.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db import _get_session_factory

logger = logging.getLogger(__name__)

_EXTRA_CONV_REF_KEY = "conv_ref"
_EXTRA_LEAD_CARD_KEY = "lead_card_activity_id"


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


class ChannelConfigService:
    """Service layer over ChannelConfig for Teams Bot operations."""

    # ------------------------------------------------------------------
    # Team lead
    # ------------------------------------------------------------------

    async def get_team_lead_aad_id(self, channel_id: str) -> Optional[str]:
        """Return the AAD OID of the registered team lead, or None."""
        async with _session() as session:
            from src.domain.repositories.channel_config_repo import ChannelConfigRepository
            config = await ChannelConfigRepository(session).get_by_channel_id(channel_id)
            if config is None or not config.team_lead_aad_id:
                return None
            return config.team_lead_aad_id

    async def set_team_lead(
        self,
        channel_id: str,
        aad_id: str,
        display_name: Optional[str] = None,
    ) -> None:
        """Register (or update) the team lead for a channel.

        Creates a ChannelConfig row if one does not yet exist.
        """
        async with _session() as session:
            from src.domain.models.channel_config import ChannelConfig
            from src.domain.repositories.channel_config_repo import ChannelConfigRepository

            repo = ChannelConfigRepository(session)
            config = await repo.get_by_channel_id(channel_id)
            if config is None:
                config = ChannelConfig(
                    channel_id=channel_id,
                    channel_name=display_name or channel_id,
                    team_lead_aad_id=aad_id,
                )
                session.add(config)
            else:
                config.team_lead_aad_id = aad_id
                if display_name:
                    config.channel_name = display_name

        logger.info(
            "ChannelConfigService: team lead set | channel=%s | aad=%s | name=%s",
            channel_id, aad_id, display_name,
        )

    # ------------------------------------------------------------------
    # ConversationReference (for proactive messaging)
    # ------------------------------------------------------------------

    async def get_conversation_reference(self, channel_id: str):
        """Return the stored ConversationReference for proactive messaging, or None."""
        raw = await self._get_extra_key(channel_id, _EXTRA_CONV_REF_KEY)
        if raw is None:
            return None
        try:
            from botbuilder.schema import ConversationReference
            return ConversationReference().deserialize(raw)
        except Exception as exc:
            logger.warning(
                "ChannelConfigService: failed to deserialize ConversationReference "
                "channel=%s error=%s", channel_id, exc,
            )
            return None

    async def set_conversation_reference(self, channel_id: str, reference) -> None:
        """Persist a ConversationReference for later proactive sends."""
        try:
            ref_dict = reference.serialize() if hasattr(reference, "serialize") else reference
        except Exception as exc:
            logger.warning(
                "ChannelConfigService: failed to serialize ConversationReference "
                "channel=%s error=%s", channel_id, exc,
            )
            return
        await self._set_extra_key(channel_id, _EXTRA_CONV_REF_KEY, ref_dict)
        logger.debug(
            "ChannelConfigService: ConversationReference saved | channel=%s", channel_id
        )

    # ------------------------------------------------------------------
    # Lead card activity_id (for in-place card updates)
    # ------------------------------------------------------------------

    async def get_lead_card_activity_id(self, channel_id: str) -> Optional[str]:
        """Return the Teams activity_id of the team-lead status card."""
        return await self._get_extra_key(channel_id, _EXTRA_LEAD_CARD_KEY)

    async def set_lead_card_activity_id(
        self, channel_id: str, activity_id: Optional[str]
    ) -> None:
        """Persist the activity_id so future updates can use update_card()."""
        if not activity_id:
            return
        await self._set_extra_key(channel_id, _EXTRA_LEAD_CARD_KEY, activity_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_extra_key(self, channel_id: str, key: str):
        """Read a value from ChannelConfig.extra_config JSON blob."""
        async with _session() as session:
            from src.domain.repositories.channel_config_repo import ChannelConfigRepository
            config = await ChannelConfigRepository(session).get_by_channel_id(channel_id)
            if config is None or not config.extra_config:
                return None
            data = json.loads(config.extra_config)
            return data.get(key)

    async def _set_extra_key(self, channel_id: str, key: str, value) -> None:
        """Write a value into ChannelConfig.extra_config JSON blob.

        Creates a minimal ChannelConfig row if one does not exist.
        """
        async with _session() as session:
            from src.domain.models.channel_config import ChannelConfig
            from src.domain.repositories.channel_config_repo import ChannelConfigRepository

            repo = ChannelConfigRepository(session)
            config = await repo.get_by_channel_id(channel_id)
            if config is None:
                config = ChannelConfig(
                    channel_id=channel_id,
                    channel_name=channel_id,
                    team_lead_aad_id="",
                )
                session.add(config)

            data = json.loads(config.extra_config) if config.extra_config else {}
            data[key] = value
            config.extra_config = json.dumps(data, ensure_ascii=False)
