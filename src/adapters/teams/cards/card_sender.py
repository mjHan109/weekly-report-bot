"""
CardSender — unified Adaptive Card delivery utility.

Methods
-------
send_card(turn_context, card)
    Send an Adaptive Card as a reply within the current turn.
    Returns the activity_id of the sent message (used for later updates).

update_card(turn_context, activity_id, card, channel_id)
    Update an existing channel message in-place using activity_id.
    On 404 (message deleted or expired), falls back to send_card() and
    returns the new activity_id — caller should persist the new ID.

proactive_send(app_id, service_url, conversation_ref, card)
    Send an Adaptive Card proactively to a channel outside of a turn.
    Used by scheduler jobs (Thu 10:00 reminder, Thu 13:00 deadline).
    No personal DMs — all proactive messages target the team channel.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from botbuilder.core import BotFrameworkAdapter, TurnContext
from botbuilder.schema import (
    Activity,
    ActivityTypes,
    Attachment,
    ConversationReference,
)

logger = logging.getLogger(__name__)


class CardSender:
    """Stateless helper — one instance per request is acceptable."""

    # ------------------------------------------------------------------
    # send_card
    # ------------------------------------------------------------------

    async def send_card(
        self,
        turn_context: TurnContext,
        card: Dict[str, Any],
    ) -> Optional[str]:
        """
        Send an Adaptive Card as a new channel message within the current turn.

        Returns the activity_id of the sent message so it can be stored for
        later in-place updates.
        """
        attachment = _wrap_adaptive_card(card)
        reply = Activity(
            type=ActivityTypes.message,
            attachments=[attachment],
        )
        response = await turn_context.send_activity(reply)
        activity_id = getattr(response, "id", None)
        logger.debug("CardSender.send_card: activity_id=%s", activity_id)
        return activity_id

    # ------------------------------------------------------------------
    # update_card
    # ------------------------------------------------------------------

    async def update_card(
        self,
        turn_context: TurnContext,
        activity_id: str,
        card: Dict[str, Any],
        channel_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Update an existing channel message in-place.

        If the update call returns 404 (original message deleted or expired),
        falls back to send_card() and logs a warning. Returns the final
        activity_id (original or new) so the caller can persist it.
        """
        attachment = _wrap_adaptive_card(card)
        updated_activity = Activity(
            id=activity_id,
            type=ActivityTypes.message,
            attachments=[attachment],
        )
        try:
            await turn_context.update_activity(updated_activity)
            logger.debug("CardSender.update_card: updated activity_id=%s", activity_id)
            return activity_id
        except Exception as exc:
            # Treat any error (including 404) as "message gone — resend"
            logger.warning(
                "CardSender.update_card: update failed (activity_id=%s) — falling back to send_card. Error: %s",
                activity_id,
                exc,
            )
            new_id = await self.send_card(turn_context=turn_context, card=card)
            return new_id

    # ------------------------------------------------------------------
    # proactive_send
    # ------------------------------------------------------------------

    async def proactive_send(
        self,
        adapter: BotFrameworkAdapter,
        app_id: str,
        conversation_ref: ConversationReference,
        card: Dict[str, Any],
    ) -> Optional[str]:
        """
        Send a card proactively to the team channel (no personal DM).

        Parameters
        ----------
        adapter          : the BotFrameworkAdapter instance
        app_id           : the bot's Microsoft App ID
        conversation_ref : ConversationReference for the target channel, stored
                           when the bot first interacted with that channel
        card             : Adaptive Card payload dict

        Returns
        -------
        activity_id of the sent message, or None on failure.
        """
        sent_activity_id: Optional[str] = None

        async def _callback(turn_context: TurnContext) -> None:
            nonlocal sent_activity_id
            activity_id = await self.send_card(turn_context=turn_context, card=card)
            sent_activity_id = activity_id

        try:
            await adapter.continue_conversation(
                reference=conversation_ref,
                callback=_callback,
                bot_app_id=app_id,
            )
        except Exception as exc:
            logger.error("CardSender.proactive_send failed: %s", exc)

        return sent_activity_id


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _wrap_adaptive_card(card: Dict[str, Any]) -> Attachment:
    """Wrap a raw Adaptive Card dict in a botbuilder Attachment."""
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )
