"""AggregationService — state machine transitions for TeamReport.

Handles two aggregation paths:

AUTO path  (deadline_service found no pending members):
  COLLECTING → AUTO_AGGREGATING → AWAITING_APPROVAL

MANUAL path (one or more late submitters):
  COLLECTING → MANUAL_PENDING
  → on every late submit: re-check if all pending members have now submitted
  → when last member submits: MANUAL_PENDING → AWAITING_APPROVAL

evaluate() is the primary entry point, called after all on-time submissions
are confirmed by deadline_service.

on_late_submit() is called by submission_service after each late submit.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AggregationMode, TeamReportStatus
from src.domain.repositories.personal_report_repo import PersonalReportRepository
from src.domain.repositories.team_report_repo import TeamReportRepository

logger = logging.getLogger(__name__)


class AggregationService:
    """Drives state machine transitions for the weekly TeamReport."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._personal_repo = PersonalReportRepository(session)
        self._team_repo = TeamReportRepository(session)

    # ── Primary entry point (called after deadline run) ───────────────────────

    async def evaluate(self, channel_id: str, week_key: str) -> TeamReportStatus:
        """Transition the TeamReport from AUTO_AGGREGATING to AWAITING_APPROVAL.

        This is called after deadline_service has set the status to
        AUTO_AGGREGATING.  If the team report is not in AUTO_AGGREGATING,
        this is a no-op.

        Args:
            channel_id: Teams channel ID (partition key).
            week_key:   ISO week key, e.g. "2026-W23".

        Returns:
            The resulting TeamReportStatus.
        """
        team_report = await self._team_repo.get_for_week(channel_id, week_key)
        if team_report is None:
            logger.warning(
                "AggregationService.evaluate: no TeamReport found for channel=%r week=%r",
                channel_id,
                week_key,
            )
            return TeamReportStatus.COLLECTING

        if team_report.status != TeamReportStatus.AUTO_AGGREGATING:
            logger.info(
                "AggregationService.evaluate: channel=%r week=%r status=%s — no-op.",
                channel_id,
                week_key,
                team_report.status,
            )
            return team_report.status

        # Transition AUTO_AGGREGATING → AWAITING_APPROVAL
        team_report.status = TeamReportStatus.AWAITING_APPROVAL
        await self._team_repo.save(team_report)

        logger.info(
            "AggregationService: channel=%r week=%r → AWAITING_APPROVAL (AUTO mode).",
            channel_id,
            week_key,
        )
        return TeamReportStatus.AWAITING_APPROVAL

    # ── Late-submit hook (called by submission_service) ───────────────────────

    async def on_late_submit(self, channel_id: str, week_key: str) -> TeamReportStatus:
        """Re-evaluate after a late submission.

        Checks whether ALL previously-pending members have now submitted.
        If so, transitions MANUAL_PENDING → AWAITING_APPROVAL.

        This is idempotent: multiple calls for the same channel+week are safe.

        Args:
            channel_id: Teams channel ID (partition key).
            week_key:   ISO week key, e.g. "2026-W23".

        Returns:
            The resulting TeamReportStatus.
        """
        team_report = await self._team_repo.get_for_week(channel_id, week_key)
        if team_report is None:
            logger.warning(
                "AggregationService.on_late_submit: no TeamReport for channel=%r week=%r",
                channel_id,
                week_key,
            )
            return TeamReportStatus.COLLECTING

        # Only act if we are in MANUAL_PENDING
        if team_report.status != TeamReportStatus.MANUAL_PENDING:
            logger.debug(
                "AggregationService.on_late_submit: channel=%r week=%r status=%s — ignoring.",
                channel_id,
                week_key,
                team_report.status,
            )
            return team_report.status

        # Check if any members are still PENDING
        remaining_pending = await self._personal_repo.list_pending(channel_id, week_key)

        if remaining_pending:
            logger.info(
                "AggregationService.on_late_submit: channel=%r week=%r — "
                "%d member(s) still pending.",
                channel_id,
                week_key,
                len(remaining_pending),
            )
            return TeamReportStatus.MANUAL_PENDING

        # All members have now submitted (some late) → ready for approval
        team_report.status = TeamReportStatus.AWAITING_APPROVAL
        await self._team_repo.save(team_report)

        logger.info(
            "AggregationService: channel=%r week=%r → AWAITING_APPROVAL "
            "(MANUAL mode — all late submits received).",
            channel_id,
            week_key,
        )
        return TeamReportStatus.AWAITING_APPROVAL

    # ── Mail-send gate ────────────────────────────────────────────────────────

    async def can_send_mail(self, channel_id: str, week_key: str) -> tuple[bool, str]:
        """Check whether conditions allow the mail to be sent.

        Rules:
          - TeamReport must be in AWAITING_APPROVAL.
          - No members may be in PENDING status (non-submitters block send).

        Args:
            channel_id: Teams channel ID (partition key).
            week_key:   ISO week key.

        Returns:
            (allowed: bool, reason: str) — if allowed is False, reason explains why.
        """
        team_report = await self._team_repo.get_for_week(channel_id, week_key)
        if team_report is None:
            return False, "TeamReport does not exist."

        if team_report.status != TeamReportStatus.AWAITING_APPROVAL:
            return False, (
                f"Mail can only be sent from AWAITING_APPROVAL state, "
                f"current status is {team_report.status!r}."
            )

        pending = await self._personal_repo.list_pending(channel_id, week_key)
        if pending:
            non_submitters = [r.aad_object_id for r in pending]
            return False, (
                f"Cannot send mail: {len(pending)} non-submitter(s) remain: "
                f"{non_submitters}."
            )

        return True, "OK"
