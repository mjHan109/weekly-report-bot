"""TeamLeadService — registration and validation of team leads.

Team leads are identified by their AAD Object ID.  The initial set is seeded
from the INITIAL_ADMIN_USER_IDS environment variable at startup.

A ChannelConfig row with team_lead_aad_id pointing to the registrant is the
source of truth for per-channel team lead authority.

Registration modes:
1. INITIAL_ADMIN_USER_IDS env var — seeded at startup (bootstrap only).
2. Self-register — any user may register themselves if their AAD ID is in
   the seed list OR the channel has no team lead yet.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.channel_config import ChannelConfig
from src.domain.repositories.channel_config_repo import ChannelConfigRepository
from src.infra.config import get_settings

logger = logging.getLogger(__name__)


class TeamLeadRegistrationError(ValueError):
    """Raised when team lead registration conditions are not met."""


class TeamLeadService:
    """Manages team lead registration and ACL checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channel_repo = ChannelConfigRepository(session)
        self._settings = get_settings()

    # ── Query helpers ─────────────────────────────────────────────────────────

    def _get_seed_ids(self) -> list[str]:
        """Return the parsed INITIAL_ADMIN_USER_IDS list.

        Raises:
            RuntimeError: If the list is empty (enforced at startup in main.py,
                          but this guard provides defence-in-depth).
        """
        ids = self._settings.initial_admin_user_ids
        if not ids:
            raise RuntimeError(
                "INITIAL_ADMIN_USER_IDS is empty. The application should have "
                "refused to start. Check startup validation in main.py."
            )
        return ids

    def is_seed_admin(self, aad_object_id: str) -> bool:
        """Return True if ``aad_object_id`` is in INITIAL_ADMIN_USER_IDS."""
        return aad_object_id in self._get_seed_ids()

    async def validate_team_lead(
        self, channel_id: str, aad_object_id: str
    ) -> bool:
        """Return True if the given AAD ID is the team lead for the channel.

        Args:
            channel_id:    Teams channel ID.
            aad_object_id: AAD Object ID of the actor to validate.

        Returns:
            True if the actor is the registered team lead for this channel.
        """
        config = await self._channel_repo.get_by_channel_id(channel_id)
        if config is None or not config.is_active:
            return False
        return config.team_lead_aad_id == aad_object_id

    # ── Registration ──────────────────────────────────────────────────────────

    async def register(
        self,
        *,
        channel_id: str,
        channel_name: str,
        requesting_aad_id: str,
        service_url: str | None = None,
    ) -> ChannelConfig:
        """Register or update a team lead for a channel.

        Registration is permitted if:
          a) The requesting AAD ID is in INITIAL_ADMIN_USER_IDS, OR
          b) The channel has no existing active config (first-time setup).

        To change a team lead after first-time setup the requester must be
        in INITIAL_ADMIN_USER_IDS (seed admin override).

        Args:
            channel_id:         Teams channel ID.
            channel_name:       Human-readable channel name.
            requesting_aad_id:  AAD Object ID of the registrant.
            service_url:        Teams Service URL for proactive messaging.

        Returns:
            The saved ChannelConfig.

        Raises:
            TeamLeadRegistrationError: If the registrant is not authorised.
        """
        existing = await self._channel_repo.get_by_channel_id(channel_id)

        is_seed = self.is_seed_admin(requesting_aad_id)
        is_first_setup = (existing is None or not existing.is_active)

        if not is_seed and not is_first_setup:
            # Channel already has a team lead and requester is not a seed admin
            raise TeamLeadRegistrationError(
                f"Only an INITIAL_ADMIN_USER_IDS member can change the team lead "
                f"for channel {channel_id!r}. "
                f"Requesting AAD ID {requesting_aad_id!r} is not authorised."
            )

        if existing is None:
            config = ChannelConfig(
                channel_id=channel_id,
                channel_name=channel_name,
                team_lead_aad_id=requesting_aad_id,
                is_active=True,
                service_url=service_url,
            )
        else:
            config = existing
            config.channel_name = channel_name
            config.team_lead_aad_id = requesting_aad_id
            config.is_active = True
            if service_url is not None:
                config.service_url = service_url

        saved = await self._channel_repo.upsert(config)
        logger.info(
            "TeamLeadService: registered aad=%r as team lead for channel=%r",
            requesting_aad_id,
            channel_id,
        )
        return saved
