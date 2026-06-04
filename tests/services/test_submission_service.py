"""Tests for SubmissionService — FR-016 (self-submit only) and FR-017 (mail block).

FR-016: Post-deadline submission is allowed only by the report owner (no proxy).
FR-017: Mail is blocked when any member remains in PENDING status.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    TEST_CHANNEL_ID,
    TEST_WEEK_KEY,
    TEAM_LEAD_AAD,
    MEMBER_AAD_1,
    MEMBER_AAD_2,
)
from src.domain.enums import ReportStatus, TeamReportStatus
from src.domain.models.personal_report import PersonalReport
from src.domain.models.team_report import TeamReport
from src.services.reports.submission_service import (
    ProxySubmissionError,
    SubmissionNotAllowedError,
    SubmissionService,
)
from src.services.reports.aggregation_service import AggregationService


# ---------------------------------------------------------------------------
# Helper — freeze time before vs after Thursday 13:00 KST (04:00 UTC)
# ---------------------------------------------------------------------------
# 2026-W23 deadline: Thursday 4 Jun 2026 13:00 KST = 04:00 UTC
_BEFORE_DEADLINE = datetime(2026, 6, 4, 3, 59, 59, tzinfo=timezone.utc)
_AT_DEADLINE     = datetime(2026, 6, 4, 4,  0,  0, tzinfo=timezone.utc)
_AFTER_DEADLINE  = datetime(2026, 6, 4, 4,  0,  1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# FR-016 — on-time submit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_time_submit_sets_status_submitted(
    async_session: AsyncSession,
    channel_config,
):
    """FR-016: A submission before the deadline must set status=SUBMITTED and
    submitted_after_deadline=False."""
    svc = SubmissionService(async_session)

    with patch(
        "src.services.reports.submission_service.datetime"
    ) as mock_dt, patch(
        "src.services.reports.submission_service.is_after_deadline",
        return_value=False,
    ):
        mock_dt.now.return_value = _BEFORE_DEADLINE
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        result = await svc.submit(
            channel_id=TEST_CHANNEL_ID,
            week_key=TEST_WEEK_KEY,
            actor_aad_id=MEMBER_AAD_1,
            target_aad_id=MEMBER_AAD_1,
            content="Weekly report content",
        )

    assert result.status == ReportStatus.SUBMITTED
    assert result.submitted_after_deadline is False


# ---------------------------------------------------------------------------
# FR-016 — late submit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_late_submit_sets_submitted_after_deadline_true(
    async_session: AsyncSession,
    channel_config,
):
    """FR-016: A submission after the deadline must set status=LATE_SUBMITTED
    and submitted_after_deadline=True (self-submit only, no proxy)."""
    # Put team report in MANUAL_PENDING so post-deadline submit is accepted
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.MANUAL_PENDING,
    )
    async_session.add(tr)
    await async_session.flush()

    svc = SubmissionService(async_session)

    # Mock on_late_submit hook to avoid circular import issues in unit test
    with patch(
        "src.services.reports.submission_service.is_after_deadline",
        return_value=True,
    ), patch.object(svc, "_fire_late_submit_hook", new=AsyncMock()):
        result = await svc.submit(
            channel_id=TEST_CHANNEL_ID,
            week_key=TEST_WEEK_KEY,
            actor_aad_id=MEMBER_AAD_1,
            target_aad_id=MEMBER_AAD_1,
            content="Late submission content",
        )

    assert result.status == ReportStatus.LATE_SUBMITTED
    assert result.submitted_after_deadline is True


# ---------------------------------------------------------------------------
# FR-016 — proxy submit blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_proxy_submit_blocked(
    async_session: AsyncSession,
    channel_config,
):
    """FR-016: actor_aad_id != target_aad_id MUST raise ProxySubmissionError
    at any time (before or after deadline). No proxy submission is ever allowed."""
    svc = SubmissionService(async_session)

    with pytest.raises(ProxySubmissionError):
        await svc.submit(
            channel_id=TEST_CHANNEL_ID,
            week_key=TEST_WEEK_KEY,
            actor_aad_id=TEAM_LEAD_AAD,   # team lead attempting proxy
            target_aad_id=MEMBER_AAD_1,   # on behalf of member — forbidden
            content="Proxy content attempt",
        )


# ---------------------------------------------------------------------------
# FR-016 — inactive / unregistered channel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_reporter_submit_blocked(async_session: AsyncSession):
    """FR-016: Submitting to a channel that is not registered or inactive must
    raise SubmissionNotAllowedError."""
    svc = SubmissionService(async_session)
    # No channel_config fixture — channel does not exist in DB

    with pytest.raises(SubmissionNotAllowedError):
        await svc.submit(
            channel_id="19:nonexistent-channel@thread.tacv2",
            week_key=TEST_WEEK_KEY,
            actor_aad_id=MEMBER_AAD_1,
            target_aad_id=MEMBER_AAD_1,
            content="Report for unknown channel",
        )


# ---------------------------------------------------------------------------
# FR-017 — can_send_mail returns False when any member is still PENDING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mail_blocked_when_any_pending(
    async_session: AsyncSession,
    channel_config,
):
    """FR-017: AggregationService.can_send_mail() must return (False, reason)
    when at least one PersonalReport row is still in PENDING status, even if
    the TeamReport is in AWAITING_APPROVAL."""
    # Team report is ready for send
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.AWAITING_APPROVAL,
    )
    async_session.add(tr)

    # Member 1 has submitted
    pr_submitted = PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=MEMBER_AAD_1,
        status=ReportStatus.SUBMITTED,
        submitted_after_deadline=False,
    )
    async_session.add(pr_submitted)

    # Member 2 is still pending — blocks mail
    pr_pending = PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=MEMBER_AAD_2,
        status=ReportStatus.PENDING,
        submitted_after_deadline=False,
    )
    async_session.add(pr_pending)
    await async_session.flush()

    agg_svc = AggregationService(async_session)
    allowed, reason = await agg_svc.can_send_mail(TEST_CHANNEL_ID, TEST_WEEK_KEY)

    assert allowed is False
    assert MEMBER_AAD_2 in reason
