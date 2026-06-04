"""Integration tests — FR-019 end-to-end flows.

test_full_auto_aggregate_flow:
  All members submit on time → DeadlineService → AUTO_AGGREGATING →
  AggregationService.evaluate() → AWAITING_APPROVAL.

test_full_manual_flow:
  One member misses deadline → MANUAL_PENDING → late self-submit →
  AggregationService.on_late_submit() → AWAITING_APPROVAL.

No external services (Graph API, LLM, Bot Framework) are called.
All interaction is with the in-memory SQLite database via real service objects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    TEST_CHANNEL_ID,
    TEST_WEEK_KEY,
    MEMBER_AAD_1,
    MEMBER_AAD_2,
)
from src.domain.enums import ReportStatus, TeamReportStatus
from src.domain.models.personal_report import PersonalReport
from src.services.reports.deadline_service import DeadlineService
from src.services.reports.aggregation_service import AggregationService
from src.services.reports.submission_service import SubmissionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _submitted_pr(aad_id: str) -> PersonalReport:
    return PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=aad_id,
        status=ReportStatus.SUBMITTED,
        submitted_after_deadline=False,
    )


# ---------------------------------------------------------------------------
# FR-019 — full AUTO aggregate flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_auto_aggregate_flow(
    async_session: AsyncSession,
    channel_config,
):
    """FR-019 (end-to-end): When all members have submitted on time:
    1. DeadlineService.run() transitions COLLECTING → AUTO_AGGREGATING.
    2. AggregationService.evaluate() transitions AUTO_AGGREGATING → AWAITING_APPROVAL.
    The report is then ready for the team lead to send via mail.
    """
    # Both members have submitted on time
    async_session.add(_submitted_pr(MEMBER_AAD_1))
    async_session.add(_submitted_pr(MEMBER_AAD_2))
    await async_session.flush()

    # Step 1: Deadline fires at 13:00
    deadline_svc = DeadlineService(async_session)
    status_after_deadline = await deadline_svc.run(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert status_after_deadline == TeamReportStatus.AUTO_AGGREGATING

    # Step 2: Auto-aggregation completes
    agg_svc = AggregationService(async_session)
    final_status = await agg_svc.evaluate(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert final_status == TeamReportStatus.AWAITING_APPROVAL

    # Step 3: Mail gate is open (no pending members)
    allowed, reason = await agg_svc.can_send_mail(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert allowed is True
    assert reason == "OK"


# ---------------------------------------------------------------------------
# FR-020 — full MANUAL flow (one late member)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_manual_flow(
    async_session: AsyncSession,
    channel_config,
):
    """FR-020 (end-to-end): When one member misses the deadline:
    1. DeadlineService.run() transitions COLLECTING → MANUAL_PENDING.
    2. The late member self-submits (no proxy allowed).
    3. SubmissionService calls on_late_submit() via the late-submit hook.
    4. AggregationService.on_late_submit() transitions MANUAL_PENDING → AWAITING_APPROVAL.
    The mail gate must then be open.
    """
    # Member 1 submitted on time; member 2 missed the deadline (PENDING)
    async_session.add(_submitted_pr(MEMBER_AAD_1))
    pr2 = PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=MEMBER_AAD_2,
        status=ReportStatus.PENDING,
        submitted_after_deadline=False,
    )
    async_session.add(pr2)
    await async_session.flush()

    # Step 1: Deadline fires — member 2 is still pending
    deadline_svc = DeadlineService(async_session)
    status_after_deadline = await deadline_svc.run(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert status_after_deadline == TeamReportStatus.MANUAL_PENDING

    # Step 2: Member 2 self-submits (late)
    # Patch is_after_deadline to True and suppress actual hook (already tested separately)
    sub_svc = SubmissionService(async_session)
    with patch(
        "src.services.reports.submission_service.is_after_deadline",
        return_value=True,
    ):
        saved = await sub_svc.submit(
            channel_id=TEST_CHANNEL_ID,
            week_key=TEST_WEEK_KEY,
            actor_aad_id=MEMBER_AAD_2,
            target_aad_id=MEMBER_AAD_2,
            content="Late report from member 2",
        )

    assert saved.status == ReportStatus.LATE_SUBMITTED
    assert saved.submitted_after_deadline is True

    # Step 3: Trigger the aggregation hook manually (the hook fires inside
    # submit when not patched; here we call it explicitly to verify state)
    agg_svc = AggregationService(async_session)
    final_status = await agg_svc.on_late_submit(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert final_status == TeamReportStatus.AWAITING_APPROVAL

    # Step 4: Mail gate is now open
    allowed, reason = await agg_svc.can_send_mail(TEST_CHANNEL_ID, TEST_WEEK_KEY)
    assert allowed is True
    assert reason == "OK"
