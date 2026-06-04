"""TeamReport ORM model.

One row per channel per ISO week.
aggregation_mode is set at Thursday 13:00 KST by deadline_service:
  AUTO   — all members submitted on time
  MANUAL — one or more members missed the deadline
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin
from src.domain.enums import AggregationMode, TeamReportStatus


class TeamReport(Base, TimestampMixin):
    """Aggregated weekly report for a channel."""

    __tablename__ = "team_reports"

    __table_args__ = (
        UniqueConstraint("channel_id", "week_key", name="uq_team_report_channel_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Mandatory partition key
    channel_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("channel_configs.channel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ISO week key, e.g. "2026-W23"
    week_key: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # State machine status
    status: Mapped[TeamReportStatus] = mapped_column(
        String(24),
        nullable=False,
        default=TeamReportStatus.COLLECTING,
        index=True,
    )

    # Set at deadline time: AUTO or MANUAL
    aggregation_mode: Mapped[AggregationMode | None] = mapped_column(
        String(8), nullable=True
    )

    # UTC deadline for this week (Thursday 13:00 KST → 04:00 UTC)
    deadline_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When the system transitioned to AUTO_AGGREGATING or MANUAL_PENDING
    aggregation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Aggregated / LLM-drafted report text (stored in MailDraft; cached here)
    aggregated_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # UTC timestamp when the team lead approved
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # AAD Object ID of team lead who approved
    approved_by_aad_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    channel: Mapped["ChannelConfig"] = relationship(
        "ChannelConfig",
        back_populates="team_reports",
    )
    personal_reports: Mapped[list["PersonalReport"]] = relationship(
        "PersonalReport",
        back_populates="team_report",
        lazy="select",
    )
    mail_drafts: Mapped[list["MailDraft"]] = relationship(
        "MailDraft",
        back_populates="team_report",
        cascade="all, delete-orphan",
        lazy="select",
    )
    revision_history: Mapped[list["RevisionHistory"]] = relationship(
        "RevisionHistory",
        back_populates="team_report",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<TeamReport channel={self.channel_id!r} week={self.week_key!r} "
            f"status={self.status} mode={self.aggregation_mode}>"
        )
