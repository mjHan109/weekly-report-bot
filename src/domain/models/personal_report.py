"""PersonalReport ORM model.

One row per member per ISO week per channel.
submitted_after_deadline=True means the member self-submitted after Thursday 13:00 KST.
Proxy submission is strictly forbidden at the service layer.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin
from src.domain.enums import ReportStatus


class PersonalReport(Base, TimestampMixin):
    """Weekly report submitted by a single team member."""

    __tablename__ = "personal_reports"

    __table_args__ = (
        # Only one report per member per channel per week
        UniqueConstraint(
            "channel_id", "aad_object_id", "week_key",
            name="uq_personal_report_member_week",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Mandatory partition key
    channel_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("channel_configs.channel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Week identifier: "YYYY-WNN" (ISO year + ISO week number), e.g. "2026-W23"
    week_key: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Submitting member's AAD Object ID
    # Must equal activity.from.aadObjectId — no proxy submission allowed
    aad_object_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Cached display name (non-authoritative)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Actual report content (raw text from the Adaptive Card form)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle status (see ReportStatus enum)
    status: Mapped[ReportStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ReportStatus.PENDING,
        index=True,
    )

    # True when the member submitted AFTER the Thursday 13:00 KST deadline
    submitted_after_deadline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # UTC timestamp of the actual submission (None while PENDING)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # FK to the parent TeamReport aggregate (set when aggregated)
    team_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    team_report: Mapped["TeamReport | None"] = relationship(
        "TeamReport",
        back_populates="personal_reports",
    )

    def __repr__(self) -> str:
        return (
            f"<PersonalReport channel={self.channel_id!r} "
            f"week={self.week_key!r} aad={self.aad_object_id!r} "
            f"status={self.status}>"
        )
