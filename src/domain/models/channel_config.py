"""ChannelConfig ORM model.

One row per Teams channel enrolled in the weekly-report workflow.
channel_id is the mandatory partition key used on every tenant-scoped query.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin


class ChannelConfig(Base, TimestampMixin):
    """Configuration record for a single Teams channel."""

    __tablename__ = "channel_configs"

    # Primary key — Teams channel ID (e.g. "19:abc...@thread.tacv2")
    channel_id: Mapped[str] = mapped_column(String(256), primary_key=True)

    # Human-readable name for display / logging
    channel_name: Mapped[str] = mapped_column(String(256), nullable=False)

    # AAD Object ID of the team lead who owns this channel's reports
    team_lead_aad_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Whether the weekly-report workflow is active for this channel
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional override: if set, reminder / deadline logic uses this timezone
    # instead of the global APP_TIMEZONE.  Stored as IANA tz string.
    timezone_override: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Teams Service URL for proactive messaging (e.g. https://smba.trafficmanager.net/…)
    service_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # JSON blob for any future per-channel feature flags
    extra_config: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    report_targets: Mapped[list["ChannelReportTarget"]] = relationship(
        "ChannelReportTarget",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="select",
    )
    team_reports: Mapped[list["TeamReport"]] = relationship(
        "TeamReport",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<ChannelConfig channel_id={self.channel_id!r} "
            f"team_lead={self.team_lead_aad_id!r}>"
        )
