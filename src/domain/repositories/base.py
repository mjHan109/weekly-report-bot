"""ChannelScopedRepository — base class enforcing channel_id isolation.

Every concrete repository MUST call ``_require_channel_id`` before executing
any query that touches tenant data.  Passing an empty or None channel_id
raises ``ValueError`` immediately so that the bug surfaces at the call site
rather than silently returning cross-channel data.
"""

import logging
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")

logger = logging.getLogger(__name__)


class ChannelScopedRepository(Generic[ModelT]):
    """Abstract base for repositories that partition data by channel_id.

    Subclasses receive an ``AsyncSession`` via constructor injection and MUST
    include ``channel_id`` in every query predicate.

    Attributes:
        _session: The SQLAlchemy async session for this unit of work.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Guard ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _require_channel_id(channel_id: str | None) -> str:
        """Assert that channel_id is a non-empty string.

        Args:
            channel_id: The channel identifier to validate.

        Returns:
            The validated (and stripped) channel_id string.

        Raises:
            ValueError: If channel_id is None, empty, or whitespace-only.
        """
        if not channel_id or not channel_id.strip():
            raise ValueError(
                "channel_id is required for all repository operations. "
                "All tenant data is partitioned by channel_id."
            )
        return channel_id.strip()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _flush(self) -> None:
        """Flush pending changes to the DB without committing."""
        await self._session.flush()

    async def _refresh(self, instance: ModelT) -> None:
        """Refresh an instance from the database."""
        await self._session.refresh(instance)
