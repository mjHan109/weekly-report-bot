"""RevisionHistory ORM model.

Records every edit made to a TeamReport's aggregated content after the initial
aggregation.  This gives the team lead a full audit trail of manual edits.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.models.base import Base, TimestampMixin


class RevisionHistory(Base, TimestampMixin):
    """Snapshot of aggregated_content before each manual edit."""

    __tablename__ = "revision_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Partition key — must match parent TeamReport.channel_id
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

    # Monotonically increasing revision number within a TeamReport
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Content snapshot **before** this revision was applied
    content_before: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content **after** this revision was applied
    content_after: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AAD Object ID of the person who made the edit
    edited_by_aad_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Short human-readable summary of the change (optional)
    change_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationship
    team_report: Mapped["TeamReport"] = relationship(
        "TeamReport",
        back_populates="revision_history",
    )

    def __repr__(self) -> str:
        return (
            f"<RevisionHistory team_report_id={self.team_report_id} "
            f"rev={self.revision_number} by={self.edited_by_aad_id!r}>"
        )
