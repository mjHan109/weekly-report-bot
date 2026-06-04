"""ReminderLog ORM model.

Tracks every reminder notification dispatched to a channel so that the
scheduler can be safely retried without double-sending.
"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.models.base import Base, TimestampMixin


class ReminderLog(Base, TimestampMixin):
    """Record of a single reminder notification sent to a channel."""

    __tablename__ = "reminder_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Partition key
    channel_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("channel_configs.channel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ISO week key the reminder relates to
    week_key: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Reminder type: "thu_1000" | "thu_1300" | "late_submit" | etc.
    reminder_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Whether delivery succeeded
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Graph API activity ID returned on successful proactive message
    activity_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Error message if delivery failed
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ReminderLog channel={self.channel_id!r} week={self.week_key!r} "
            f"type={self.reminder_type!r} delivered={self.delivered}>"
        )
