"""SubmissionService — handles personal report submission with all business rules.

Key rules enforced here:
1. Proxy prevention: actor_aad_id MUST equal target_aad_id.
2. On-time detection: submission before Thursday 13:00 KST → SUBMITTED.
3. Late detection: submission after deadline → LATE_SUBMITTED + submitted_after_deadline=True.
4. Post-deadline flow: only self-submission is allowed; team lead cannot proxy.
5. After a late submission, aggregation_service.on_late_submit() is called
   so it can re-evaluate whether all pending members have now submitted.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import ReportStatus, TeamReportStatus
from src.domain.models.personal_report import PersonalReport
from src.domain.repositories.channel_config_repo import ChannelConfigRepository
from src.domain.repositories.personal_report_repo import PersonalReportRepository
from src.domain.repositories.team_report_repo import TeamReportRepository
from src.services.reports.week_utils import is_after_deadline

logger = logging.getLogger(__name__)


class ProxySubmissionError(PermissionError):
    """Raised when actor_aad_id != target_aad_id (no proxy submission allowed)."""


class SubmissionNotAllowedError(PermissionError):
    """Raised when submission is not permitted in the current state."""


class SubmissionService:
    """Handles the full lifecycle of a personal weekly report submission."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channel_repo = ChannelConfigRepository(session)
        self._personal_repo = PersonalReportRepository(session)
        self._team_repo = TeamReportRepository(session)

    async def submit(
        self,
        *,
        channel_id: str,
        week_key: str,
        actor_aad_id: str,
        target_aad_id: str,
        content: str,
        display_name: str | None = None,
    ) -> PersonalReport:
        """Submit a personal weekly report.

        Args:
            channel_id:    Teams channel ID (partition key).
            week_key:      ISO week key, e.g. "2026-W23".
            actor_aad_id:  AAD Object ID from the incoming Bot activity
                           (activity.from.aadObjectId).
            target_aad_id: AAD Object ID of the person the report is for.
            content:       The report body text.
            display_name:  Optional cached display name.

        Returns:
            The saved PersonalReport.

        Raises:
            ProxySubmissionError:      If actor_aad_id != target_aad_id.
            SubmissionNotAllowedError: If the channel or state machine disallows it.
            ValueError:                If channel_id or week_key are invalid.
        """
        # ── Rule 1: No proxy submission — ever ────────────────────────────────
        if actor_aad_id != target_aad_id:
            logger.warning(
                "Proxy submission attempt blocked: actor=%r tried to submit for target=%r "
                "in channel=%r week=%r",
                actor_aad_id,
                target_aad_id,
                channel_id,
                week_key,
            )
            raise ProxySubmissionError(
                f"Proxy submission is not allowed. "
                f"Actor {actor_aad_id!r} cannot submit on behalf of {target_aad_id!r}."
            )

        # ── Validate channel is active ─────────────────────────────────────
        config = await self._channel_repo.get_by_channel_id(channel_id)
        if config is None or not config.is_active:
            raise SubmissionNotAllowedError(
                f"Channel {channel_id!r} is not registered or inactive."
            )

        # ── Determine timing ───────────────────────────────────────────────
        now_utc = datetime.now(tz=timezone.utc)
        after_deadline = is_after_deadline(week_key, now_utc)

        # ── Validate TeamReport state for late submissions ─────────────────
        team_report = await self._team_repo.get_for_week(channel_id, week_key)
        if after_deadline and team_report is not None:
            # Post-deadline: only allowed when in MANUAL_PENDING
            if team_report.status not in (
                TeamReportStatus.MANUAL_PENDING,
                TeamReportStatus.COLLECTING,  # race condition: scheduler not yet run
            ):
                raise SubmissionNotAllowedError(
                    f"Cannot submit after deadline when team report status is "
                    f"{team_report.status!r}. Late submissions are only accepted "
                    f"in MANUAL_PENDING state."
                )

        # ── Fetch or create the PersonalReport row ─────────────────────────
        report = await self._personal_repo.get(channel_id, week_key, target_aad_id)

        if report is None:
            report = PersonalReport(
                channel_id=channel_id,
                week_key=week_key,
                aad_object_id=target_aad_id,
            )

        if report.status in (ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED):
            logger.info(
                "Re-submission: overwriting existing %s report for aad=%r channel=%r week=%r",
                report.status,
                target_aad_id,
                channel_id,
                week_key,
            )

        # ── Update report fields ───────────────────────────────────────────
        report.content = content
        report.display_name = display_name
        report.submitted_at = now_utc
        report.submitted_after_deadline = after_deadline

        if after_deadline:
            report.status = ReportStatus.LATE_SUBMITTED
            logger.info(
                "Late submission: aad=%r channel=%r week=%r",
                target_aad_id,
                channel_id,
                week_key,
            )
        else:
            report.status = ReportStatus.SUBMITTED
            logger.info(
                "On-time submission: aad=%r channel=%r week=%r",
                target_aad_id,
                channel_id,
                week_key,
            )

        saved = await self._personal_repo.save(report)

        # ── Hook: notify aggregation service on late submit ────────────────
        if after_deadline:
            await self._fire_late_submit_hook(channel_id, week_key)

        return saved

    async def _fire_late_submit_hook(
        self, channel_id: str, week_key: str
    ) -> None:
        """Trigger re-evaluation after a late submission.

        Imported lazily to avoid a circular import between submission and
        aggregation services.
        """
        from src.services.reports.aggregation_service import AggregationService  # noqa: PLC0415

        aggregation_svc = AggregationService(self._session)
        await aggregation_svc.on_late_submit(channel_id, week_key)
