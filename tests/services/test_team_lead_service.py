"""Tests for TeamLeadService — FR-014 (team lead registration) and
FR-018 (reporter assignment: team lead only).

FR-014: Only a seed admin (INITIAL_ADMIN_USER_IDS) or the user doing
        first-time setup may register themselves as team lead.
FR-018: Assigning report targets is a team-lead-only operation.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    TEST_CHANNEL_ID,
    TEAM_LEAD_AAD,
    MEMBER_AAD_1,
    SEED_ADMIN_AAD,
)
from src.domain.models.channel_config import ChannelConfig
from src.services.acl.team_lead_service import (
    TeamLeadService,
    TeamLeadRegistrationError,
)


# ---------------------------------------------------------------------------
# Helpers — build a Settings stub with a known seed list
# ---------------------------------------------------------------------------

def _patch_settings(seed_ids: list[str]):
    """Return a context manager that patches get_settings() with given seed IDs."""
    mock_settings = MagicMock()
    mock_settings.initial_admin_user_ids = seed_ids
    mock_settings.initial_admin_user_ids_raw = ",".join(seed_ids)
    return patch(
        "src.services.acl.team_lead_service.get_settings",
        return_value=mock_settings,
    )


# ---------------------------------------------------------------------------
# FR-014 — seed admin can always register
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_allowed_for_initial_admin(
    async_session: AsyncSession,
):
    """FR-014: A user in INITIAL_ADMIN_USER_IDS must be able to register as
    team lead for any channel, even if one already exists."""
    # Create existing config with a different team lead
    existing = ChannelConfig(
        channel_id=TEST_CHANNEL_ID,
        channel_name="Existing Channel",
        team_lead_aad_id=TEAM_LEAD_AAD,
        is_active=True,
    )
    async_session.add(existing)
    await async_session.flush()

    with _patch_settings([SEED_ADMIN_AAD]):
        svc = TeamLeadService(async_session)
        config = await svc.register(
            channel_id=TEST_CHANNEL_ID,
            channel_name="Existing Channel",
            requesting_aad_id=SEED_ADMIN_AAD,
        )

    assert config.team_lead_aad_id == SEED_ADMIN_AAD


# ---------------------------------------------------------------------------
# FR-014 — first-time setup allowed for anyone
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_allowed_for_self(async_session: AsyncSession):
    """FR-014: Any user may self-register as team lead for a channel that has
    no existing active configuration (first-time channel setup)."""
    with _patch_settings([SEED_ADMIN_AAD]):
        svc = TeamLeadService(async_session)
        config = await svc.register(
            channel_id=TEST_CHANNEL_ID,
            channel_name="New Channel",
            requesting_aad_id=MEMBER_AAD_1,   # not a seed admin
        )

    assert config.team_lead_aad_id == MEMBER_AAD_1
    assert config.is_active is True


# ---------------------------------------------------------------------------
# FR-014 — non-admin non-self change is blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_blocked_for_non_admin_non_self(
    async_session: AsyncSession,
):
    """FR-014: Attempting to change an existing team lead by a user who is
    neither in INITIAL_ADMIN_USER_IDS nor doing first-time setup must raise
    TeamLeadRegistrationError."""
    # Channel already has a team lead
    existing = ChannelConfig(
        channel_id=TEST_CHANNEL_ID,
        channel_name="Channel With Lead",
        team_lead_aad_id=TEAM_LEAD_AAD,
        is_active=True,
    )
    async_session.add(existing)
    await async_session.flush()

    with _patch_settings([SEED_ADMIN_AAD]):
        svc = TeamLeadService(async_session)
        with pytest.raises(TeamLeadRegistrationError):
            await svc.register(
                channel_id=TEST_CHANNEL_ID,
                channel_name="Channel With Lead",
                requesting_aad_id=MEMBER_AAD_1,   # not seed admin, channel exists
            )


# ---------------------------------------------------------------------------
# FR-014 — missing INITIAL_ADMIN_USER_IDS raises RuntimeError at startup
# ---------------------------------------------------------------------------

def test_missing_initial_admin_ids_raises_at_startup():
    """FR-014: _get_seed_ids() must raise RuntimeError when
    INITIAL_ADMIN_USER_IDS is empty, simulating the startup guard that
    prevents the application from booting without admin seeds."""
    mock_settings = MagicMock()
    mock_settings.initial_admin_user_ids = []   # empty list

    with patch(
        "src.services.acl.team_lead_service.get_settings",
        return_value=mock_settings,
    ):
        mock_session = MagicMock()
        svc = TeamLeadService(mock_session)
        with pytest.raises(RuntimeError, match="INITIAL_ADMIN_USER_IDS is empty"):
            svc._get_seed_ids()


# ---------------------------------------------------------------------------
# FR-018 — only team lead may assign reporters (validate_team_lead)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assign_reporters_team_lead_only(
    async_session: AsyncSession,
    channel_config: ChannelConfig,
):
    """FR-018: validate_team_lead() must return True only for the registered
    team lead and False for any other AAD ID (including ordinary members)."""
    with _patch_settings([SEED_ADMIN_AAD]):
        svc = TeamLeadService(async_session)

        is_lead = await svc.validate_team_lead(TEST_CHANNEL_ID, TEAM_LEAD_AAD)
        is_member = await svc.validate_team_lead(TEST_CHANNEL_ID, MEMBER_AAD_1)

    assert is_lead is True
    assert is_member is False
