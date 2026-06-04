"""TeamReportRepository — CRUD for TeamReport rows."""

import logging
from typing import Sequence

from sqlalchemy import select

from src.domain.enums import TeamReportStatus
from src.domain.models.team_report import TeamReport
from src.domain.repositories.base import ChannelScopedRepository

logger = logging.getLogger(__name__)


class TeamReportRepository(ChannelScopedRepository[TeamReport]):
    """All queries are scoped by channel_id (mandatory partition key)."""

    async def get_for_week(
        self, channel_id: str, week_key: str
    ) -> TeamReport | None:
        """Fetch a TeamReport by channel + week key."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(TeamReport).where(
                TeamReport.channel_id == cid,
                TeamReport.week_key == week_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, channel_id: str, report_id: int) -> TeamReport | None:
        """Fetch by primary key, enforcing channel_id isolation."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(TeamReport).where(
                TeamReport.id == report_id,
                TeamReport.channel_id == cid,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        channel_id: str,
        status: TeamReportStatus,
    ) -> Sequence[TeamReport]:
        """Return all TeamReports for a channel in a given status."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(TeamReport).where(
                TeamReport.channel_id == cid,
                TeamReport.status == status,
            )
        )
        return result.scalars().all()

    async def get_or_create(
        self,
        channel_id: str,
        week_key: str,
    ) -> tuple[TeamReport, bool]:
        """Return (TeamReport, created) for the given channel+week.

        Creates a new COLLECTING row if one does not already exist.
        """
        cid = self._require_channel_id(channel_id)
        existing = await self.get_for_week(cid, week_key)
        if existing is not None:
            return existing, False

        team_report = TeamReport(
            channel_id=cid,
            week_key=week_key,
            status=TeamReportStatus.COLLECTING,
        )
        self._session.add(team_report)
        await self._flush()
        await self._refresh(team_report)
        logger.info(
            "Created TeamReport for channel=%r week=%r", cid, week_key
        )
        return team_report, True

    async def save(self, report: TeamReport) -> TeamReport:
        """Persist changes to a TeamReport."""
        self._require_channel_id(report.channel_id)
        self._session.add(report)
        await self._flush()
        await self._refresh(report)
        return report
