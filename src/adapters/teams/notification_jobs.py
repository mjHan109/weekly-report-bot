"""
Notification jobs — proactive channel message delivery for scheduled alerts.

These functions are called by the scheduler (infra/scheduler) at:
  - Thursday 10:00 KST : post_reminder_card()
  - Thursday 13:00 KST : post_deadline_card()

All messages are sent to the **team channel** — no personal DMs.
@mentions are embedded in the card body (msteams.entities) so Teams
delivers in-app notifications to the mentioned reporters.

Both functions resolve the bot adapter and conversation reference from the
application context; they do NOT require an active turn context.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)


def _current_iso_week() -> str:
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def post_reminder_card(channel_id: str) -> None:
    """
    Post the Thursday 10:00 reminder card to the specified team channel.

    Steps
    -----
    1. Load the BotFrameworkAdapter and app credentials from environment.
    2. Retrieve the stored ConversationReference for channel_id.
    3. Fetch the list of reporters who have NOT yet submitted this week.
    4. Build reminder_1000 card with @mentions.
    5. Post proactively via CardSender.proactive_send().
    """
    logger.info("notification_jobs: post_reminder_card | channel=%s", channel_id)

    adapter, app_id = _get_adapter_and_app_id()
    if adapter is None:
        logger.error("post_reminder_card: adapter not available")
        return

    conversation_ref = await _get_conversation_ref(channel_id)
    if conversation_ref is None:
        logger.error(
            "post_reminder_card: no conversation reference stored for channel=%s",
            channel_id,
        )
        return

    pending = await _get_pending_reporter_mentions(channel_id)
    report_week = _current_iso_week()

    from src.adapters.teams.cards.reminder_1000 import build_reminder_1000_card
    from src.adapters.teams.cards.card_sender import CardSender

    card = build_reminder_1000_card(
        pending_reporter_mentions=pending,
        channel_id=channel_id,
        report_week=report_week,
    )
    sender = CardSender()
    activity_id = await sender.proactive_send(
        adapter=adapter,
        app_id=app_id,
        conversation_ref=conversation_ref,
        card=card,
    )
    logger.info(
        "post_reminder_card: sent | channel=%s | activity_id=%s | pending=%d",
        channel_id,
        activity_id,
        len(pending),
    )


async def post_deadline_card(channel_id: str) -> None:
    """
    Post the Thursday 13:00 deadline alert card to the specified team channel.

    Steps
    -----
    1. Load adapter and app credentials.
    2. Retrieve stored ConversationReference.
    3. Fetch submission counts and pending reporter list.
    4. Build deadline_1300 card.
    5. Post proactively.
    6. If all submitted, trigger auto-aggregation immediately.
    """
    logger.info("notification_jobs: post_deadline_card | channel=%s", channel_id)

    adapter, app_id = _get_adapter_and_app_id()
    if adapter is None:
        logger.error("post_deadline_card: adapter not available")
        return

    conversation_ref = await _get_conversation_ref(channel_id)
    if conversation_ref is None:
        logger.error(
            "post_deadline_card: no conversation reference stored for channel=%s",
            channel_id,
        )
        return

    pending = await _get_pending_reporter_mentions(channel_id)
    total_count = await _get_total_reporter_count(channel_id)
    submitted_count = total_count - len(pending)
    report_week = _current_iso_week()

    from src.adapters.teams.cards.deadline_1300 import build_deadline_1300_card
    from src.adapters.teams.cards.card_sender import CardSender

    card = build_deadline_1300_card(
        pending_reporter_mentions=pending,
        submitted_count=submitted_count,
        total_count=total_count,
        channel_id=channel_id,
        report_week=report_week,
    )
    sender = CardSender()
    activity_id = await sender.proactive_send(
        adapter=adapter,
        app_id=app_id,
        conversation_ref=conversation_ref,
        card=card,
    )
    logger.info(
        "post_deadline_card: sent | channel=%s | activity_id=%s | pending=%d | total=%d",
        channel_id,
        activity_id,
        len(pending),
        total_count,
    )

    # If all submitted at deadline time, kick off auto-aggregation
    if not pending:
        logger.info(
            "post_deadline_card: all submitted — triggering auto-aggregation for channel=%s",
            channel_id,
        )
        await _trigger_auto_aggregation(channel_id, report_week)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_adapter_and_app_id():
    """Return (BotFrameworkAdapter, app_id) from the running application context."""
    try:
        from src.api.app import get_adapter, get_app_id  # type: ignore
        return get_adapter(), get_app_id()
    except ImportError:
        logger.warning("App context not available — adapter stub returns None")
        return None, os.environ.get("MICROSOFT_APP_ID", "")


async def _get_conversation_ref(channel_id: str):
    """Retrieve stored ConversationReference for a channel."""
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        return await ChannelConfigService().get_conversation_reference(channel_id)
    except ImportError:
        return None


async def _get_pending_reporter_mentions(
    channel_id: str,
) -> List[dict]:
    """Return [{aad_id, display_name}] for reporters who have not yet submitted."""
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_pending_reporter_mentions(channel_id)
    except ImportError:
        logger.warning("ReportService not available — returning empty pending list")
        return []


async def _get_total_reporter_count(channel_id: str) -> int:
    """Return the total number of designated reporters for this channel."""
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_total_reporter_count(channel_id)
    except ImportError:
        return 0


async def _trigger_auto_aggregation(channel_id: str, report_week: str) -> None:
    """Trigger LLM aggregation and update the team-lead status card."""
    try:
        from src.services.llm.aggregation_service import AggregationService
        from src.services.reports.channel_config_service import ChannelConfigService
        from src.adapters.teams.cards.aggregate_preview import build_aggregate_preview_card

        aggregated_text = await AggregationService().aggregate_weekly_reports(channel_id)

        # We don't have a turn_context here, so we send a new proactive card
        adapter, app_id = _get_adapter_and_app_id()
        if adapter is None:
            return

        conversation_ref = await _get_conversation_ref(channel_id)
        if conversation_ref is None:
            return

        card = build_aggregate_preview_card(
            aggregated_text=aggregated_text,
            channel_id=channel_id,
            report_week=report_week,
        )
        from src.adapters.teams.cards.card_sender import CardSender
        sender = CardSender()
        new_activity_id = await sender.proactive_send(
            adapter=adapter,
            app_id=app_id,
            conversation_ref=conversation_ref,
            card=card,
        )
        # Persist the new activity_id for future in-place updates
        await ChannelConfigService().set_lead_card_activity_id(channel_id, new_activity_id)

    except ImportError as exc:
        logger.warning("Auto-aggregation services not available: %s", exc)
    except Exception as exc:
        logger.error("Auto-aggregation failed for channel=%s: %s", channel_id, exc)
