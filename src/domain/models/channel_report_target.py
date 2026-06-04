"""ChannelReportTarget ORM model.

Each row represents one member who is expected to submit a weekly report
in the given channel.  The team lead designates targets via the bot command.
"""

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin


class ChannelReportTarget(Base, TimestampMixin):
    """A single person expected to submit a report in a channel."""

    __tablename__ = "channel_report_targets"

    __table_args__ = (
        # Each member can appear at most once per channel
        UniqueConstraint("channel_id", "aad_object_id", name="uq_target_channel_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Mandatory partition key — must match ChannelConfig.channel_id
    channel_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("channel_configs.channel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Azure AD Object ID of the team member
    aad_object_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Display name (cached from Graph; non-authoritative)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # UPN / email used when sending the final report mail
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Soft-delete: set to False to remove a member without losing history
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship back to channel config
    channel: Mapped["ChannelConfig"] = relationship(
        "ChannelConfig",
        back_populates="report_targets",
    )

    def __repr__(self) -> str:
        return (
            f"<ChannelReportTarget channel={self.channel_id!r} "
            f"aad={self.aad_object_id!r}>"
        )
