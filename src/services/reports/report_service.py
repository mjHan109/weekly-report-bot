"""
ReportService — facade used by Slack (and Teams) adapters.

Wraps DB session management and delegates to the underlying domain
repositories and services. Adapter handlers call this without knowing
about AsyncSession or SQLAlchemy.

Methods
-------
  is_designated_reporter(user_id, channel_id) -> bool
  has_submitted_this_week(user_id, channel_id) -> bool
  get_pending_reporter_mentions(channel_id) -> list[dict]
  get_total_reporter_count(channel_id) -> int
  is_team_lead(user_id, channel_id) -> bool
  get_team_lead(channel_id) -> str | None
  register_team_lead(user_id, channel_id) -> None
  set_designated_reporters(channel_id, user_ids) -> None
  submit_report(user_id, channel_id, content, is_late) -> None
  resolve_slack_to_aad(slack_user_id) -> str
  auto_link_slack_user(slack_user_id, client) -> str
  get_unsubmitted_with_slack_ids(channel_id) -> list[dict]
  send_unsubmitted_reminders(channel_id, client) -> int
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from src.infra.db import _get_session_factory
from src.services.reports.week_utils import current_week_key

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a new AsyncSession with auto-commit on success."""
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


class ReportService:
    """Stateless facade — creates a fresh DB session per call."""

    # ── Reporter ACL ──────────────────────────────────────────────────────────

    async def is_designated_reporter(self, user_id: str, channel_id: str) -> bool:
        """Return True if user_id is an active report target for channel_id."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                repo = ChannelConfigRepository(session)
                targets = await repo.get_active_targets(channel_id)
                return any(t.aad_object_id == user_id for t in targets)
        except Exception as exc:
            logger.warning("is_designated_reporter failed: %s — returning False", exc)
            return False

    async def has_submitted_this_week(self, user_id: str, channel_id: str) -> bool:
        """Return True if the user already submitted a report this week."""
        try:
            async with _session() as session:
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.enums import ReportStatus
                repo = PersonalReportRepository(session)
                week_key = current_week_key()
                report = await repo.get(channel_id, week_key, user_id)
                return report is not None and report.status in (
                    ReportStatus.SUBMITTED,
                    ReportStatus.LATE_SUBMITTED,
                )
        except Exception as exc:
            logger.warning("has_submitted_this_week failed: %s — returning False", exc)
            return False

    async def get_pending_reporter_mentions(
        self, channel_id: str
    ) -> list[dict]:
        """Return [{aad_id, display_name}] for reporters who haven't submitted yet."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.enums import ReportStatus

                config_repo = ChannelConfigRepository(session)
                report_repo = PersonalReportRepository(session)
                week_key = current_week_key()

                targets = await config_repo.get_active_targets(channel_id)
                submitted_ids: set[str] = set()
                for report in await report_repo.list_for_week(channel_id, week_key):
                    if report.status in (ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED):
                        submitted_ids.add(report.aad_object_id)

                return [
                    {"aad_id": t.aad_object_id, "display_name": t.display_name or t.aad_object_id}
                    for t in targets
                    if t.aad_object_id not in submitted_ids
                ]
        except Exception as exc:
            logger.warning("get_pending_reporter_mentions failed: %s — returning []", exc)
            return []

    async def get_total_reporter_count(self, channel_id: str) -> int:
        """Return the count of active designated reporters for a channel."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                repo = ChannelConfigRepository(session)
                targets = await repo.get_active_targets(channel_id)
                return len(targets)
        except Exception as exc:
            logger.warning("get_total_reporter_count failed: %s — returning 0", exc)
            return 0

    # ── Team Lead ACL ─────────────────────────────────────────────────────────

    async def is_team_lead(self, user_id: str, channel_id: str) -> bool:
        """Return True if user_id is registered as team lead for channel_id."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                repo = ChannelConfigRepository(session)
                config = await repo.get_by_channel_id(channel_id)
                return config is not None and config.team_lead_aad_id == user_id
        except Exception as exc:
            logger.warning("is_team_lead failed: %s — returning False", exc)
            return False

    async def get_team_lead(self, channel_id: str) -> str | None:
        """Return the team lead AAD object ID for a channel, or None."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                repo = ChannelConfigRepository(session)
                config = await repo.get_by_channel_id(channel_id)
                return config.team_lead_aad_id if config else None
        except Exception as exc:
            logger.warning("get_team_lead failed: %s — returning None", exc)
            return None

    async def register_team_lead(self, user_id: str, channel_id: str) -> None:
        """Register or update the team lead for a channel."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                from src.domain.models.channel_config import ChannelConfig
                repo = ChannelConfigRepository(session)
                config = await repo.get_by_channel_id(channel_id)
                if config is None:
                    config = ChannelConfig(
                        channel_id=channel_id,
                        channel_name=channel_id,  # will be updated later
                        team_lead_aad_id=user_id,
                    )
                else:
                    config.team_lead_aad_id = user_id
                    config.is_active = True
                await repo.upsert(config)
                logger.info("Registered team lead: user=%s channel=%s", user_id, channel_id)
        except Exception as exc:
            logger.error("register_team_lead failed: %s", exc)
            raise

    # ── Reporter assignment ───────────────────────────────────────────────────

    async def set_designated_reporters(
        self, channel_id: str, user_ids: list[str], display_names: dict[str, str] | None = None
    ) -> None:
        """Replace the active reporter list for a channel with user_ids."""
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                from src.domain.models.channel_report_target import ChannelReportTarget
                repo = ChannelConfigRepository(session)

                # Deactivate all existing targets
                existing = await repo.get_active_targets(channel_id)
                for target in existing:
                    target.is_active = False

                # Insert or reactivate new targets
                for uid in user_ids:
                    result = await session.execute(
                        select(ChannelReportTarget).where(
                            ChannelReportTarget.channel_id == channel_id,
                            ChannelReportTarget.aad_object_id == uid,
                        )
                    )
                    target = result.scalar_one_or_none()
                    name = (display_names or {}).get(uid)
                    if target is None:
                        target = ChannelReportTarget(
                            channel_id=channel_id,
                            aad_object_id=uid,
                            display_name=name,
                        )
                        session.add(target)
                    else:
                        target.is_active = True
                        if name:
                            target.display_name = name

                logger.info(
                    "Set %d designated reporters for channel=%s", len(user_ids), channel_id
                )
        except Exception as exc:
            logger.error("set_designated_reporters failed: %s", exc)
            raise

    # ── Slack ↔ AAD user mapping ──────────────────────────────────────────────

    async def resolve_slack_to_aad(self, slack_user_id: str) -> str:
        """Return the AAD object ID linked to slack_user_id, or slack_user_id as fallback.

        Falls back to slack_user_id so existing flows continue to work when the
        org directory has not yet been synced or the user is not yet linked.
        """
        try:
            async with _session() as session:
                from src.domain.repositories.org_user_repo import OrgUserRepository
                repo = OrgUserRepository(session)
                user = await repo.get_by_slack_id(slack_user_id)
                return user.aad_object_id if user else slack_user_id
        except Exception as exc:
            logger.warning("resolve_slack_to_aad failed: %s — using slack_user_id", exc)
            return slack_user_id

    async def auto_link_slack_user(self, slack_user_id: str, client) -> str:
        """Fetch the user's email from Slack profile, link to OrgUser, return aad_object_id.

        Calls the Slack API (users_info) to get the profile email, then upserts
        the slack_user_id onto the matching OrgUser row.
        Returns aad_object_id if linked, slack_user_id as fallback.
        """
        try:
            resp = await client.users_info(user=slack_user_id)
            email = resp["user"]["profile"].get("email", "")
            if not email:
                logger.warning("auto_link: no email in Slack profile for %s", slack_user_id)
                return slack_user_id

            async with _session() as session:
                from src.domain.repositories.org_user_repo import OrgUserRepository
                repo = OrgUserRepository(session)

                # Check if already linked
                existing = await repo.get_by_slack_id(slack_user_id)
                if existing:
                    return existing.aad_object_id

                # Link by email
                user = await repo.link_slack_id_by_email(email, slack_user_id)
                if user:
                    logger.info(
                        "Linked Slack %s → AAD %s via email %s",
                        slack_user_id, user.aad_object_id, email,
                    )
                    return user.aad_object_id

            logger.warning("auto_link: no OrgUser found for email=%s", email)
            return slack_user_id
        except Exception as exc:
            logger.warning("auto_link_slack_user failed: %s — fallback to slack_user_id", exc)
            return slack_user_id

    # ── 미제출자 리마인드 ─────────────────────────────────────────────────────

    async def get_unsubmitted_with_slack_ids(self, channel_id: str) -> list[dict]:
        """Return pending reporters with their Slack user IDs for DM reminders.

        Returns list of {aad_id, display_name, slack_user_id} where slack_user_id
        may be None if the user hasn't been linked yet.
        """
        try:
            async with _session() as session:
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.repositories.org_user_repo import OrgUserRepository
                from src.domain.enums import ReportStatus

                config_repo = ChannelConfigRepository(session)
                report_repo = PersonalReportRepository(session)
                org_repo = OrgUserRepository(session)
                week_key = current_week_key()

                targets = await config_repo.get_active_targets(channel_id)
                submitted_ids = await report_repo.get_submitted_aad_ids(channel_id, week_key)

                result = []
                for t in targets:
                    if t.aad_object_id not in submitted_ids:
                        org_user = await org_repo.get_by_aad_id(t.aad_object_id)
                        result.append({
                            "aad_id": t.aad_object_id,
                            "display_name": t.display_name or t.aad_object_id,
                            "slack_user_id": org_user.slack_user_id if org_user else None,
                        })
                return result
        except Exception as exc:
            logger.warning("get_unsubmitted_with_slack_ids failed: %s", exc)
            return []

    async def send_unsubmitted_reminders(self, channel_id: str, client) -> int:
        """Send DM reminders to reporters who haven't submitted this week.

        Returns the number of DMs sent.
        """
        unsubmitted = await self.get_unsubmitted_with_slack_ids(channel_id)
        sent = 0
        for reporter in unsubmitted:
            slack_id = reporter.get("slack_user_id")
            if not slack_id:
                logger.warning(
                    "No slack_user_id for aad=%s — cannot send reminder DM",
                    reporter["aad_id"],
                )
                continue
            try:
                dm = await client.conversations_open(users=slack_id)
                dm_channel = dm["channel"]["id"]
                await client.chat_postMessage(
                    channel=dm_channel,
                    text=(
                        f"⏰ *주간 보고 제출 알림*\n\n"
                        f"아직 이번 주 보고서를 제출하지 않으셨습니다.\n"
                        f"`/주간보고` 명령어로 지금 제출해주세요!"
                    ),
                )
                sent += 1
                logger.info("Reminder DM sent to %s", slack_id)
            except Exception as exc:
                logger.warning("Failed to send reminder to %s: %s", slack_id, exc)
        return sent

    # ── Draft (임시저장) ──────────────────────────────────────────────────────

    async def save_draft(
        self,
        user_id: str,
        channel_id: str,
        content: str,
        client=None,
    ) -> None:
        """Upsert a PersonalReport with DRAFT status (임시저장).

        Creates or overwrites the PENDING/DRAFT row for this user/channel/week.
        Does NOT change rows that are already SUBMITTED or LATE_SUBMITTED.
        """
        try:
            if client is not None:
                aad_id = await self.auto_link_slack_user(user_id, client)
            else:
                aad_id = await self.resolve_slack_to_aad(user_id)

            async with _session() as session:
                from src.domain.models.personal_report import PersonalReport
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.enums import ReportStatus

                week_key = current_week_key()
                repo = PersonalReportRepository(session)
                report = await repo.get(channel_id, week_key, aad_id)

                if report is not None and report.status in (
                    ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED
                ):
                    # Already submitted — don't overwrite with a draft
                    return

                if report is None:
                    report = PersonalReport(
                        channel_id=channel_id,
                        week_key=week_key,
                        aad_object_id=aad_id,
                    )

                report.content = content
                report.status = ReportStatus.DRAFT
                await repo.save(report)
                logger.debug("Draft saved: slack=%s aad=%s channel=%s", user_id, aad_id, channel_id)
        except Exception as exc:
            # Non-fatal: in-memory state still drives the flow
            logger.warning("save_draft failed (non-fatal): %s", exc)

    async def get_draft_report(
        self, user_id: str, channel_id: str
    ) -> dict | None:
        """Return the current week's DRAFT report content, or None.

        Returns {content: str, week_key: str} if a DRAFT exists.
        """
        try:
            aad_id = await self.resolve_slack_to_aad(user_id)
            async with _session() as session:
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.enums import ReportStatus
                repo = PersonalReportRepository(session)
                week_key = current_week_key()
                report = await repo.get(channel_id, week_key, aad_id)
                if report is not None and report.status == ReportStatus.DRAFT:
                    return {"content": report.content or "", "week_key": week_key}
        except Exception as exc:
            logger.warning("get_draft_report failed: %s", exc)
        return None

    # ── Submission ────────────────────────────────────────────────────────────

    async def submit_report(
        self,
        user_id: str,
        channel_id: str,
        content: str,
        is_late: bool,
        client=None,
    ) -> None:
        """Save a personal report via SubmissionService.

        Resolves Slack user_id → AAD object ID via OrgUser mapping.
        If client is provided, auto-links via Slack profile email when no mapping exists.
        """
        try:
            # Resolve Slack user_id to AAD object ID
            if client is not None:
                aad_id = await self.auto_link_slack_user(user_id, client)
            else:
                aad_id = await self.resolve_slack_to_aad(user_id)

            async with _session() as session:
                from src.services.reports.submission_service import SubmissionService
                from src.domain.repositories.audit_log_repo import AuditLogRepository
                week_key = current_week_key()
                svc = SubmissionService(session)
                report = await svc.submit(
                    channel_id=channel_id,
                    week_key=week_key,
                    actor_aad_id=aad_id,
                    target_aad_id=aad_id,
                    content=content,
                )
                event_type = "report.late_submit" if is_late else "report.submit"
                await AuditLogRepository(session).append(
                    event_type=event_type,
                    actor_aad_id=aad_id,
                    channel_id=channel_id,
                    week_key=week_key,
                    personal_report_id=getattr(report, "id", None),
                    payload={"slack_user_id": user_id, "is_late": is_late},
                )
                logger.info(
                    "Report submitted: slack=%s aad=%s channel=%s week=%s late=%s",
                    user_id, aad_id, channel_id, week_key, is_late,
                )
        except Exception as exc:
            logger.error("submit_report failed: %s", exc)
            raise
