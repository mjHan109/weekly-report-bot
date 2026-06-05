"""
MessageSender — wraps the Slack WebClient for proactive channel posting.

Equivalent to Teams CardSender.proactive_send().
Used by notification_jobs.py to post scheduled messages.
"""

from __future__ import annotations

import logging
from typing import Optional

from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


class MessageSender:

    def __init__(self, token: str) -> None:
        self._client = AsyncWebClient(token=token)

    async def post_to_channel(
        self,
        channel_id: str,
        message: dict,
    ) -> Optional[str]:
        """
        Post a Block Kit message to a channel.

        Returns the message timestamp (ts) on success, None on failure.
        """
        try:
            resp = await self._client.chat_postMessage(
                channel=channel_id,
                **message,
            )
            ts: str = resp["ts"]
            logger.info("MessageSender: posted to channel=%s ts=%s", channel_id, ts)
            return ts
        except Exception as exc:
            logger.error(
                "MessageSender: failed to post to channel=%s: %s", channel_id, exc
            )
            return None

    async def update_message(
        self,
        channel_id: str,
        ts: str,
        message: dict,
    ) -> bool:
        """Update an existing message (e.g., replace pending card after all submit)."""
        try:
            await self._client.chat_update(
                channel=channel_id,
                ts=ts,
                **message,
            )
            return True
        except Exception as exc:
            logger.error(
                "MessageSender: failed to update channel=%s ts=%s: %s",
                channel_id, ts, exc,
            )
            return False
