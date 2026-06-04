"""AuditLog ORM model.

Immutable append-only record of all significant events (submit, aggregate,
approve, send, admin changes).  Rows are never updated or deleted.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.models.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Immutable event log for compliance and debugging."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Partition key (nullable for system-level events not tied to a channel)
    channel_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True, index=True
    )

    # ISO week key of the event (nullable for non-report events)
    week_key: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    # Actor who triggered the event (AAD Object ID, or "system" for automated)
    actor_aad_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Verb describing the action, e.g. "report.submit", "report.late_submit",
    # "team_report.aggregate_auto", "mail.send", "admin.register_team_lead"
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Optional FK to the affected PersonalReport
    personal_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional FK to the affected TeamReport
    team_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # JSON payload with event-specific details (non-sensitive)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} event={self.event_type!r} "
            f"actor={self.actor_aad_id!r}>"
        )
