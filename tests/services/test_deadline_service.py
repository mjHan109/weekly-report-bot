"""Tests for DeadlineService — FR-013, FR-015, FR-019, FR-020.

FR-013: Thu 10:00 reminder targets only non-submitters.
FR-015: At 13:00 deadline, non-submitters trigger MANUAL_PENDING.
FR-019: At 13:00, if all submitted → AUTO_AGGREGATING.
FR-020: Manual path is only triggered when missing reports exist.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    TEST_CHANNEL_ID,
    TEST_WEEK_KEY,
    MEMBER_AAD_1,
    MEMBER_AAD_2,
)
from src.domain.enums import ReportStatus, TeamReportStatus, AggregationMode
from src.domain.models.personal_report import PersonalReport
from src.domain.models.team_report import TeamReport
from src.services.reports.deadline_service import DeadlineService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _submitted(aad_id: str) -> PersonalReport:
    return PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=aad_id,
        status=ReportStatus.SUBMITTED,
        submitted_after_deadline=False,
    )


def _pending(aad_id: str) -> PersonalReport:
    return PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=aad_id,
        status=ReportStatus.PENDING,
        submitted_after_deadline=False,
    )


# ---------------------------------------------------------------------------
# FR-019 — all submitted → AUTO_AGGREGATING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deadline_run_auto_mode_when_all_submitted(
    async_session: AsyncSession,
    channel_config,
):
    """FR-019: DeadlineService.run() must set status=AUTO_AGGREGATING and
    aggregation_mode=AUTO when all PersonalReport rows for the week are
    in SUBMITTED (none in PENDING)."""
    async_session.add(_submitted(MEMBER_AAD_1))
    async_session.add(_submitted(MEMBER_AAD_2))
    await async_session.flush()

    svc = DeadlineService(async_session)
    result = await svc.run(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.AUTO_AGGREGATING

    from src.domain.repositories.team_report_repo import TeamReportRepository
    repo = TeamReportRepository(async_session)
    tr = await repo.get_for_week(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert tr is not None
    assert tr.status == TeamReportStatus.AUTO_AGGREGATING
    assert tr.aggregation_mode == AggregationMode.AUTO


# ---------------------------------------------------------------------------
# FR-015 / FR-020 — missing reports → MANUAL_PENDING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deadline_run_manual_mode_when_missing(
    async_session: AsyncSession,
    channel_config,
):
    """FR-015 + FR-020: DeadlineService.run() must set status=MANUAL_PENDING
    and aggregation_mode=MANUAL when at least one member has not submitted by
    the 13:00 KST deadline."""
    async_session.add(_submitted(MEMBER_AAD_1))
    async_session.add(_pending(MEMBER_AAD_2))   # member 2 missed deadline
    await async_session.flush()

    svc = DeadlineService(async_session)
    result = await svc.run(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.MANUAL_PENDING

    from src.domain.repositories.team_report_repo import TeamReportRepository
    repo = TeamReportRepository(async_session)
    tr = await repo.get_for_week(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert tr is not None
    assert tr.status == TeamReportStatus.MANUAL_PENDING
    assert tr.aggregation_mode == AggregationMode.MANUAL


# ---------------------------------------------------------------------------
# Idempotency — skip when not COLLECTING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deadline_run_idempotent(
    async_session: AsyncSession,
    channel_config,
):
    """FR-019 + FR-020: DeadlineService.run() is idempotent. Calling it when
    the TeamReport is already past COLLECTING must return the current status
    without modifying the row."""
    # Pre-set team report as MANUAL_PENDING (deadline already ran)
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)
    await async_session.flush()

    svc = DeadlineService(async_session)
    result = await svc.run(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    # Must return the existing status unchanged
    assert result == TeamReportStatus.MANUAL_PENDING

    await async_session.refresh(tr)
    # aggregation_mode remains None (not overwritten)
    assert tr.aggregation_mode is None


# ---------------------------------------------------------------------------
# FR-013 — reminder targets only non-submitters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reminder_job_targets_only_non_submitters(
    async_session: AsyncSession,
    channel_config,
):
    """FR-013: The 10:00 reminder logic must identify non-submitters correctly.
    Members with status=PENDING are non-submitters; members with
    status=SUBMITTED must NOT receive a reminder.

    This test validates the PersonalReportRepository.list_pending() contract
    that the reminder job depends on, since DeadlineService re-uses the same
    query at 13:00 (FR-015)."""
    async_session.add(_submitted(MEMBER_AAD_1))
    async_session.add(_pending(MEMBER_AAD_2))
    await async_session.flush()

    from src.domain.repositories.personal_report_repo import PersonalReportRepository
    repo = PersonalReportRepository(async_session)
    pending = await repo.list_pending(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    aad_ids = [r.aad_object_id for r in pending]
    assert MEMBER_AAD_2 in aad_ids
    assert MEMBER_AAD_1 not in aad_ids
