"""OrgUser — Microsoft 365 directory user, synced from Graph API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.models.base import Base


class OrgUser(Base):
    """Cached copy of Azure AD user records.

    Synced by UserSyncService via GET /users (Application permission).
    Used for mail recipient auto-complete and team lookup.
    """

    __tablename__ = "org_users"

    # Azure AD object ID — primary key (immutable per user)
    aad_object_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    display_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True, index=True)
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    manager_aad_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    manager_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)

    # Slack workspace user ID — linked manually or auto-detected on first /주간보고
    slack_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, unique=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
