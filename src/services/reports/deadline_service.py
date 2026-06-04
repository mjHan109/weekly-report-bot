"""DeadlineService — determines AUTO vs MANUAL mode at Thursday 13:00 KST.

Called by the scheduler at exactly Thu 13:00 KST (04:00 UTC) via
POST /internal/scheduler/deadline.

Business rules:
  - If TeamReport is not in COLLECTING status → skip (idempotent).
  - If all targets have submitted on time → transition to AUTO_AGGREGATING.
  - If any target is still PENDING → transition to MANUAL_PENDING.
  - Record deadline_utc and aggregation_mode on the TeamReport.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AggregationMode, TeamReportStatus
from src.domain.repositories.channel_config_repo import ChannelConfigRepository
from src.domain.repositories.personal_report_repo import PersonalReportRepository
from src.domain.repositories.team_report_repo import TeamReportRepository
from src.services.reports.week_utils import get_week_deadline

logger = logging.getLogger(__name__)


class DeadlineService:
    """Evaluates the collection state at deadline time for one channel+week."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channel_repo = ChannelConfigRepository(session)
        self._personal_repo = PersonalReportRepository(session)
        self._team_repo = TeamReportRepository(session)

    async def run(self, channel_id: str, week_key: str) -> TeamReportStatus:
        """Execute deadline logic for (channel_id, week_key).

        This method is idempotent: if the TeamReport is not in COLLECTING
        status it returns the current status without any side effects.

        Args:
            channel_id: Teams channel ID (partition key).
            week_key:   ISO week key, e.g. "2026-W23".

        Returns:
            The resulting TeamReportStatus after processing.
        """
        team_report, _ = await self._team_repo.get_or_create(channel_id, week_key)

        # ── Idempotency guard ─────────────────────────────────────────────────
        if team_report.status != TeamReportStatus.COLLECTING:
            logger.info(
                "DeadlineService: channel=%r week=%r already in status=%s — skipping.",
                channel_id,
                week_key,
                team_report.status,
            )
            return team_report.status

        # ── Determine mode ────────────────────────────────────────────────────
        pending_reports = await self._personal_repo.list_pending(channel_id, week_key)
        now_utc = datetime.now(tz=timezone.utc)
        deadline_utc = get_week_deadline(week_key)

        if pending_reports:
            # One or more members have not submitted
            new_status = TeamReportStatus.MANUAL_PENDING
            mode = AggregationMode.MANUAL
            logger.info(
                "DeadlineService: channel=%r week=%r — %d non-submitter(s) found → MANUAL_PENDING.",
                channel_id,
                week_key,
                len(pending_reports),
            )
        else:
            # Everyone submitted on time
            new_status = TeamReportStatus.AUTO_AGGREGATING
            mode = AggregationMode.AUTO
            logger.info(
                "DeadlineService: channel=%r week=%r — all submitted → AUTO_AGGREGATING.",
                channel_id,
                week_key,
            )

        team_report.status = new_status
        team_report.aggregation_mode = mode
        team_report.deadline_utc = deadline_utc
        team_report.aggregation_started_at = now_utc

        await self._team_repo.save(team_report)
        return new_status
