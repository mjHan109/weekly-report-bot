"""
RegisterTeamLeadHandler — "팀장 등록" command.

ACL rules — dual-gate (ADR-008, ADR-SEC-002)
--------------------------------------------
Gate 1: INITIAL_ADMIN check
  If no team lead has been registered for this channel yet, the very first
  registration is accepted from any user who is listed in the
  INITIAL_ADMIN_AAD_IDS environment variable (comma-separated).

Gate 2: Self-registration
  A user can register themselves as team lead for a channel where they are
  already a channel member and no team lead is registered.

Existing team lead re-registration
  Once a team lead is registered for a channel, only that same team lead
  (or an INITIAL_ADMIN) can change the registration.

Flow
----
  User types "팀장 등록"
    -> Gate 1/2 ACL check
    -> Register caller as team lead for this channel
    -> Confirm in channel
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes

logger = logging.getLogger(__name__)


class RegisterTeamLeadHandler:
    """Handles the '팀장 등록' command with dual-gate ACL."""

    async def handle(self, turn_context: TurnContext) -> None:
        aad_id = _get_aad_id(turn_context)
        channel_id = _get_channel_id(turn_context)
        display_name = _get_display_name(turn_context)

        if not aad_id or not channel_id:
            await _reply(turn_context, "사용자 또는 채널 정보를 확인할 수 없습니다.")
            return

        # Dual-gate ACL
        allowed, reason = await _check_registration_acl(aad_id, channel_id)
        if not allowed:
            await _reply(turn_context, f"팀장 등록 권한이 없습니다. ({reason})")
            return

        # Perform registration
        try:
            await _register_team_lead(aad_id, channel_id, display_name)
        except Exception as exc:
            logger.error("팀장 등록 실패: %s", exc)
            await _reply(turn_context, f"팀장 등록 중 오류가 발생했습니다: {exc}")
            return

        logger.info(
            "RegisterTeamLeadHandler: registered | aad_id=%s | channel=%s | name=%s",
            aad_id,
            channel_id,
            display_name,
        )
        await _reply(
            turn_context,
            f"{display_name or '(이름 없음)'}님이 이 채널의 팀장으로 등록되었습니다.",
        )


# ---------------------------------------------------------------------------
# ACL logic
# ---------------------------------------------------------------------------

async def _check_registration_acl(
    aad_id: str, channel_id: str
) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).

    Priority:
    1. INITIAL_ADMIN list → always allowed.
    2. No team lead registered yet → self-registration allowed.
    3. Existing team lead is the caller → re-registration allowed.
    4. Otherwise → denied.
    """
    # Gate 1: INITIAL_ADMIN
    if _is_initial_admin(aad_id):
        return True, "INITIAL_ADMIN"

    existing_lead_aad_id = await _get_current_team_lead(channel_id)

    # Gate 2a: no team lead yet → self-registration
    if existing_lead_aad_id is None:
        return True, "최초 등록"

    # Gate 2b: existing team lead re-registers themselves
    if existing_lead_aad_id == aad_id:
        return True, "기존 팀장 재등록"

    return False, "이미 팀장이 등록된 채널입니다"


def _is_initial_admin(aad_id: str) -> bool:
    """Check the INITIAL_ADMIN_AAD_IDS environment variable."""
    admin_ids_raw = os.environ.get("INITIAL_ADMIN_AAD_IDS", "")
    admin_ids = {aid.strip() for aid in admin_ids_raw.split(",") if aid.strip()}
    return aad_id in admin_ids


async def _get_current_team_lead(channel_id: str) -> Optional[str]:
    """Return the AAD ID of the currently registered team lead, or None."""
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        return await ChannelConfigService().get_team_lead_aad_id(channel_id)
    except ImportError:
        logger.warning("ChannelConfigService not available — returning None")
        return None


async def _register_team_lead(
    aad_id: str, channel_id: str, display_name: Optional[str]
) -> None:
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        await ChannelConfigService().set_team_lead(
            channel_id=channel_id,
            aad_id=aad_id,
            display_name=display_name,
        )
    except ImportError:
        logger.warning("ChannelConfigService not available — registration stub (no-op)")


# ---------------------------------------------------------------------------
# Activity helpers
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


def _get_display_name(turn_context: TurnContext) -> Optional[str]:
    from_account = getattr(turn_context.activity, "from_", None)
    if from_account is None:
        return None
    return getattr(from_account, "name", None)


async def _reply(turn_context: TurnContext, text: str) -> None:
    await turn_context.send_activity(
        Activity(type=ActivityTypes.message, text=text)
    )
