"""SQLAlchemy declarative base and shared mixins."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""

    # Subclasses may override __tablename__ or use the default derived form.
    type_annotation_map: dict[type, Any] = {}


class TimestampMixin:
    """Adds created_at / updated_at columns to any ORM model.

    Both columns are stored as UTC timestamps with timezone info.
    updated_at is refreshed automatically by the DB on every UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
