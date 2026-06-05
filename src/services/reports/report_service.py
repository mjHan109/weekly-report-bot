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

    # ── Submission ────────────────────────────────────────────────────────────

    async def submit_report(
        self,
        user_id: str,
        channel_id: str,
        content: str,
        is_late: bool,
    ) -> None:
        """Save a personal report via SubmissionService."""
        try:
            async with _session() as session:
                from src.services.reports.submission_service import SubmissionService
                week_key = current_week_key()
                svc = SubmissionService(session)
                await svc.submit(
                    channel_id=channel_id,
                    week_key=week_key,
                    actor_aad_id=user_id,
                    target_aad_id=user_id,
                    content=content,
                )
                logger.info(
                    "Report submitted: user=%s channel=%s week=%s late=%s",
                    user_id, channel_id, week_key, is_late,
                )
        except Exception as exc:
            logger.error("submit_report failed: %s", exc)
            raise
