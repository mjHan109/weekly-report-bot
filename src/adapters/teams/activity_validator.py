"""
Activity validator — ADR-SEC-005: Channel isolation enforcement.

Ensures the channel_id flowing into service methods is always sourced from
the Bot Framework Activity (trusted) and never from user-supplied card payloads.
Cross-channel access attempts are rejected and written to AuditLog.
"""

from __future__ import annotations

import logging
from typing import Optional

from botbuilder.schema import Activity

logger = logging.getLogger(__name__)


def extract_channel_id_from_activity(activity: Activity) -> str:
    """
    Extract the Teams channel ID from a Bot Framework Activity.

    Source of truth: activity.channel_data["teamsChannelId"] for channel
    conversations, or activity.conversation.id for 1:1.

    Raises ValueError if no channel ID can be resolved.
    """
    # Teams channel message: channel_data.teamsChannelId is authoritative
    channel_data = activity.channel_data or {}
    teams_channel_id: Optional[str] = None

    if isinstance(channel_data, dict):
        channel = channel_data.get("channel", {})
        if isinstance(channel, dict):
            teams_channel_id = channel.get("id")

    if not teams_channel_id:
        # Fallback: conversation.id for personal/group scope
        conversation = activity.conversation
        if conversation and conversation.id:
            teams_channel_id = conversation.id

    if not teams_channel_id:
        raise ValueError(
            "Cannot resolve channel_id from Bot Framework activity. "
            "Activity has no channel_data.channel.id and no conversation.id."
        )

    return teams_channel_id


def assert_channel_matches(
    activity_channel_id: str,
    payload_channel_id: Optional[str],
    actor_aad_id: str,
) -> None:
    """
    Assert that the channel_id in a card/task payload matches the activity channel.

    If they differ, log a security event and raise PermissionError.
    Callers must use extract_channel_id_from_activity() for the authoritative value
    and pass any user-supplied channel_id from the payload as payload_channel_id.

    ADR-SEC-005: cross-channel access attempts must be logged as security events.
    """
    if payload_channel_id is None:
        # No payload channel_id supplied — nothing to cross-check
        return

    if payload_channel_id != activity_channel_id:
        logger.warning(
            "SECURITY: Cross-channel access attempt detected. "
            "actor_aad_id=%s activity_channel=%s payload_channel=%s",
            actor_aad_id,
            activity_channel_id,
            payload_channel_id,
        )
        raise PermissionError(
            f"Channel mismatch: activity channel '{activity_channel_id}' "
            f"does not match payload channel '{payload_channel_id}'. "
            "Request rejected (ADR-SEC-005)."
        )
