"""Tests for AggregationService — FR-019 (auto-aggregate) and FR-020 (manual aggregate).

FR-019: When all members submit on time the system transitions to
        AUTO_AGGREGATING → AWAITING_APPROVAL automatically.
FR-020: When any member misses the deadline the report enters MANUAL_PENDING;
        once every late member has submitted it transitions to AWAITING_APPROVAL.
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
from src.domain.enums import ReportStatus, TeamReportStatus
from src.domain.models.personal_report import PersonalReport
from src.domain.models.team_report import TeamReport
from src.services.reports.aggregation_service import AggregationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_personal_report(
    channel_id: str,
    week_key: str,
    aad_object_id: str,
    status: ReportStatus,
) -> PersonalReport:
    return PersonalReport(
        channel_id=channel_id,
        week_key=week_key,
        aad_object_id=aad_object_id,
        status=status,
        submitted_after_deadline=(status == ReportStatus.LATE_SUBMITTED),
    )


# ---------------------------------------------------------------------------
# FR-019 — auto aggregate path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_aggregate_when_all_on_time(
    async_session: AsyncSession,
    channel_config,
):
    """FR-019: evaluate() on an AUTO_AGGREGATING team report must transition it
    to AWAITING_APPROVAL. This is the happy path when every member submitted
    before the deadline."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.AUTO_AGGREGATING,
    )
    async_session.add(tr)
    await async_session.flush()

    svc = AggregationService(async_session)
    result = await svc.evaluate(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.AWAITING_APPROVAL

    # Reload from DB
    await async_session.refresh(tr)
    assert tr.status == TeamReportStatus.AWAITING_APPROVAL


# ---------------------------------------------------------------------------
# FR-020 — manual pending when any member is late
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_pending_when_any_late(
    async_session: AsyncSession,
    channel_config,
):
    """FR-020: When the team report is in MANUAL_PENDING and a pending member
    is still present, on_late_submit() must keep the status as MANUAL_PENDING."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)

    # Member 1 submitted, member 2 is still pending
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_1, ReportStatus.SUBMITTED
    ))
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_2, ReportStatus.PENDING
    ))
    await async_session.flush()

    svc = AggregationService(async_session)
    result = await svc.on_late_submit(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.MANUAL_PENDING


@pytest.mark.asyncio
async def test_manual_pending_when_any_missing(
    async_session: AsyncSession,
    channel_config,
):
    """FR-020: on_late_submit() with at least one PENDING report must not
    transition out of MANUAL_PENDING — the team lead cannot aggregate until all
    members have submitted."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)
    # Both members are still pending
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_1, ReportStatus.PENDING
    ))
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_2, ReportStatus.PENDING
    ))
    await async_session.flush()

    svc = AggregationService(async_session)
    result = await svc.on_late_submit(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.MANUAL_PENDING


# ---------------------------------------------------------------------------
# FR-020 — missing count decreases after each late submit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_late_submit_updates_missing_count(
    async_session: AsyncSession,
    channel_config,
):
    """FR-020: After a late submit changes MEMBER_AAD_2 from PENDING to
    LATE_SUBMITTED, on_late_submit() must see exactly one remaining PENDING
    member and keep MANUAL_PENDING status."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)

    # Member 1 remains pending; member 2 has just submitted (late)
    pr1 = _make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_1, ReportStatus.PENDING
    )
    pr2 = _make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_2, ReportStatus.LATE_SUBMITTED
    )
    async_session.add(pr1)
    async_session.add(pr2)
    await async_session.flush()

    svc = AggregationService(async_session)
    result = await svc.on_late_submit(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    # Member 1 still pending → stay in MANUAL_PENDING
    assert result == TeamReportStatus.MANUAL_PENDING


# ---------------------------------------------------------------------------
# FR-019/FR-020 — all submitted after late → AWAITING_APPROVAL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_submitted_after_late_sets_all_complete(
    async_session: AsyncSession,
    channel_config,
):
    """FR-020: When the last PENDING member submits (late), on_late_submit()
    must transition MANUAL_PENDING → AWAITING_APPROVAL, enabling the team lead
    to send the mail (FR-019 completion via manual path)."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)

    # Both members have now submitted (one late, one on time)
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_1, ReportStatus.SUBMITTED
    ))
    async_session.add(_make_personal_report(
        TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_2, ReportStatus.LATE_SUBMITTED
    ))
    await async_session.flush()

    svc = AggregationService(async_session)
    result = await svc.on_late_submit(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert result == TeamReportStatus.AWAITING_APPROVAL
    await async_session.refresh(tr)
    assert tr.status == TeamReportStatus.AWAITING_APPROVAL
