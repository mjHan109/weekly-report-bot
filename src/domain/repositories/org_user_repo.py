"""OrgUserRepository — CRUD for Azure AD user cache."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select, or_, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.org_user import OrgUser


class OrgUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(self, users: list[dict]) -> int:
        """Insert or update a batch of user dicts from Graph API.

        Each dict must have at minimum: aad_object_id.
        Returns the number of rows affected.
        """
        if not users:
            return 0

        # SQLite upsert — on conflict update all columns
        stmt = sqlite_insert(OrgUser).values(users)
        stmt = stmt.on_conflict_do_update(
            index_elements=["aad_object_id"],
            set_={
                "display_name": stmt.excluded.display_name,
                "email": stmt.excluded.email,
                "department": stmt.excluded.department,
                "job_title": stmt.excluded.job_title,
                "manager_aad_id": stmt.excluded.manager_aad_id,
                "manager_email": stmt.excluded.manager_email,
                "synced_at": func.now(),
            },
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def search(self, query: str, limit: int = 20) -> Sequence[OrgUser]:
        """Search by display_name or email (case-insensitive partial match)."""
        q = f"%{query.lower()}%"
        stmt = (
            select(OrgUser)
            .where(
                or_(
                    func.lower(OrgUser.display_name).like(q),
                    func.lower(OrgUser.email).like(q),
                )
            )
            .order_by(OrgUser.display_name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_departments(self) -> list[str]:
        """Return distinct non-null department names, sorted."""
        stmt = (
            select(OrgUser.department)
            .where(OrgUser.department.isnot(None))
            .distinct()
            .order_by(OrgUser.department)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_by_department(self, department: str) -> Sequence[OrgUser]:
        """Return all users in a given department."""
        stmt = (
            select(OrgUser)
            .where(OrgUser.department == department)
            .order_by(OrgUser.display_name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_aad_id(self, aad_object_id: str) -> OrgUser | None:
        result = await self._session.execute(
            select(OrgUser).where(OrgUser.aad_object_id == aad_object_id)
        )
        return result.scalar_one_or_none()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(OrgUser))
        return result.scalar_one()

    async def get_by_slack_id(self, slack_user_id: str) -> OrgUser | None:
        """Return OrgUser linked to a Slack user ID, or None if not yet linked."""
        result = await self._session.execute(
            select(OrgUser).where(OrgUser.slack_user_id == slack_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> OrgUser | None:
        """Return OrgUser by exact email match (case-insensitive)."""
        result = await self._session.execute(
            select(OrgUser).where(func.lower(OrgUser.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def link_slack_id(self, aad_object_id: str, slack_user_id: str) -> bool:
        """Associate a Slack user ID with an existing OrgUser.

        Returns True if the row was found and updated, False if aad_object_id not found.
        Raises if slack_user_id is already linked to a different user (UNIQUE constraint).
        """
        user = await self.get_by_aad_id(aad_object_id)
        if user is None:
            return False
        user.slack_user_id = slack_user_id
        return True

    async def link_slack_id_by_email(self, email: str, slack_user_id: str) -> OrgUser | None:
        """Find OrgUser by email then set slack_user_id.

        Used for auto-linking on first /주간보고 command.
        Returns the updated OrgUser, or None if email not found in directory.
        """
        user = await self.get_by_email(email)
        if user is None:
            return None
        user.slack_user_id = slack_user_id
        return user
