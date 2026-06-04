"""PersonalReportRepository — CRUD for PersonalReport rows."""

import logging
from typing import Sequence

from sqlalchemy import select

from src.domain.enums import ReportStatus
from src.domain.models.personal_report import PersonalReport
from src.domain.repositories.base import ChannelScopedRepository

logger = logging.getLogger(__name__)


class PersonalReportRepository(ChannelScopedRepository[PersonalReport]):
    """All queries are scoped by channel_id (mandatory partition key)."""

    async def get(
        self,
        channel_id: str,
        week_key: str,
        aad_object_id: str,
    ) -> PersonalReport | None:
        """Fetch one PersonalReport by composite key."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(PersonalReport).where(
                PersonalReport.channel_id == cid,
                PersonalReport.week_key == week_key,
                PersonalReport.aad_object_id == aad_object_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, channel_id: str, report_id: int) -> PersonalReport | None:
        """Fetch by primary key, enforcing channel_id isolation."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(PersonalReport).where(
                PersonalReport.id == report_id,
                PersonalReport.channel_id == cid,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_week(
        self, channel_id: str, week_key: str
    ) -> Sequence[PersonalReport]:
        """Return all PersonalReports for a channel+week (all statuses)."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(PersonalReport).where(
                PersonalReport.channel_id == cid,
                PersonalReport.week_key == week_key,
            )
        )
        return result.scalars().all()

    async def list_pending(
        self, channel_id: str, week_key: str
    ) -> Sequence[PersonalReport]:
        """Return PENDING reports for a channel+week (not yet submitted)."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(PersonalReport).where(
                PersonalReport.channel_id == cid,
                PersonalReport.week_key == week_key,
                PersonalReport.status == ReportStatus.PENDING,
            )
        )
        return result.scalars().all()

    async def list_submitted(
        self, channel_id: str, week_key: str
    ) -> Sequence[PersonalReport]:
        """Return SUBMITTED + LATE_SUBMITTED reports for a channel+week."""
        cid = self._require_channel_id(channel_id)
        result = await self._session.execute(
            select(PersonalReport).where(
                PersonalReport.channel_id == cid,
                PersonalReport.week_key == week_key,
                PersonalReport.status.in_(
                    [ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED]
                ),
            )
        )
        return result.scalars().all()

    async def save(self, report: PersonalReport) -> PersonalReport:
        """Insert or update a PersonalReport."""
        self._require_channel_id(report.channel_id)
        self._session.add(report)
        await self._flush()
        await self._refresh(report)
        return report

    async def count_pending(self, channel_id: str, week_key: str) -> int:
        """Count members who have not yet submitted for the given week."""
        pending = await self.list_pending(channel_id, week_key)
        return len(pending)
