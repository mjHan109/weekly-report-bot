"""MailDraft ORM model.

Stores the Graph-API-ready mail payload that the team lead reviews before
approving.  Only one draft is active at a time per TeamReport (latest wins).
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin


class MailDraft(Base, TimestampMixin):
    """Draft email ready for Graph API /sendMail."""

    __tablename__ = "mail_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Partition key
    channel_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("channel_configs.channel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    team_report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("team_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Mail subject line
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)

    # HTML body (Graph API uses HTML for mail body)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plain-text fallback / summary
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON array string of recipient objects: [{"email": "...", "name": "..."}]
    recipients_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Whether this is the currently active draft for the team report
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Whether this draft was actually sent
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Graph message-id returned on successful send
    graph_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationship
    team_report: Mapped["TeamReport"] = relationship(
        "TeamReport",
        back_populates="mail_drafts",
    )

    def __repr__(self) -> str:
        return (
            f"<MailDraft id={self.id} team_report_id={self.team_report_id} "
            f"sent={self.is_sent}>"
        )
