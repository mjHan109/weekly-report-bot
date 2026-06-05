"""
Notification jobs — proactive Slack channel messages for scheduled alerts.

Called by the scheduler at:
  - Thursday 10:00 KST : post_reminder_message()
  - Thursday 13:00 KST : post_deadline_message()

Both functions use MessageSender (Slack WebClient wrapper) to post
Block Kit messages directly to the channel — no turn context needed.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def _current_iso_week() -> str:
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _get_sender():
    """Return a MessageSender instance using the configured Slack bot token."""
    from src.infra.config import get_settings
    from src.adapters.slack.blocks.message_sender import MessageSender
    settings = get_settings()
    return MessageSender(token=settings.slack_bot_token)


async def post_reminder_message(channel_id: str) -> None:
    """Post the Thursday 10:00 reminder to the channel."""
    logger.info("notification_jobs: post_reminder_message | channel=%s", channel_id)

    pending = await _get_pending_user_ids(channel_id)
    report_week = _current_iso_week()

    from src.adapters.slack.blocks.reminder_1000 import build_reminder_1000_message
    msg = build_reminder_1000_message(
        pending_user_ids=pending,
        channel_id=channel_id,
        report_week=report_week,
    )

    sender = _get_sender()
    ts = await sender.post_to_channel(channel_id=channel_id, message=msg)
    logger.info(
        "post_reminder_message: done | channel=%s | ts=%s | pending=%d",
        channel_id, ts, len(pending),
    )


async def post_deadline_message(channel_id: str) -> None:
    """Post the Thursday 13:00 deadline alert to the channel."""
    logger.info("notification_jobs: post_deadline_message | channel=%s", channel_id)

    pending = await _get_pending_user_ids(channel_id)
    total_count = await _get_total_reporter_count(channel_id)
    submitted_count = total_count - len(pending)
    report_week = _current_iso_week()

    from src.adapters.slack.blocks.deadline_1300 import build_deadline_1300_message
    msg = build_deadline_1300_message(
        pending_user_ids=pending,
        submitted_count=submitted_count,
        total_count=total_count,
        channel_id=channel_id,
        report_week=report_week,
    )

    sender = _get_sender()
    ts = await sender.post_to_channel(channel_id=channel_id, message=msg)
    logger.info(
        "post_deadline_message: done | channel=%s | ts=%s | submitted=%d/%d",
        channel_id, ts, submitted_count, total_count,
    )

    # All submitted at deadline → auto-aggregate
    if not pending:
        logger.info("All submitted — triggering auto-aggregation for channel=%s", channel_id)
        await _trigger_auto_aggregation(channel_id, report_week, sender)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _get_pending_user_ids(channel_id: str) -> list[str]:
    try:
        from src.services.reports.report_service import ReportService
        items = await ReportService().get_pending_reporter_mentions(channel_id)
        return [item["aad_id"] for item in items]
    except ImportError:
        logger.warning("ReportService not available — empty pending list")
        return []


async def _get_total_reporter_count(channel_id: str) -> int:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_total_reporter_count(channel_id)
    except ImportError:
        return 0


async def _trigger_auto_aggregation(channel_id: str, report_week: str, sender) -> None:
    try:
        from src.services.llm.aggregation_service import AggregationService
        aggregated_text = await AggregationService().aggregate_weekly_reports(channel_id)

        from src.adapters.slack.blocks.aggregate_preview import build_aggregate_preview_message
        msg = build_aggregate_preview_message(
            aggregated_text=aggregated_text,
            channel_id=channel_id,
            report_week=report_week,
        )
        await sender.post_to_channel(channel_id=channel_id, message=msg)
    except ImportError as exc:
        logger.warning("Auto-aggregation services not available: %s", exc)
    except Exception as exc:
        logger.error("Auto-aggregation failed for channel=%s: %s", channel_id, exc)
