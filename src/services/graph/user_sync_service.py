"""
UserSyncService — syncs Azure AD users into the local org_users table.

Usage
-----
    service = UserSyncService()
    result = await service.sync_all()
    # {"synced": 250, "pages": 3}

Requires Application permissions in Azure AD:
    User.Read.All
    (Directory.Read.All for manager lookup)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.config import get_settings
from src.infra.db import _get_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


class UserSyncService:

    def __init__(self) -> None:
        settings = get_settings()
        from src.services.graph.app_client import GraphAppClient
        self._client = GraphAppClient(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )

    async def sync_all(self, fetch_managers: bool = False) -> dict[str, int]:
        """
        Fetch all users from Graph and upsert into org_users.

        Parameters
        ----------
        fetch_managers:
            If True, also call GET /users/{id}/manager for each user.
            Adds many API calls — use only when Directory.Read.All is granted.

        Returns
        -------
        {"synced": <total rows>, "pages": <page count>}
        """
        total = 0
        pages = 0

        for page in self._client.list_users_pages():
            pages += 1
            rows = [self._map_user(u) for u in page]

            if fetch_managers:
                rows = await self._attach_managers(rows, page)

            async with _session() as session:
                from src.domain.repositories.org_user_repo import OrgUserRepository
                repo = OrgUserRepository(session)
                affected = await repo.upsert_batch(rows)
                total += len(rows)
                logger.info(
                    "UserSyncService: page=%d users=%d affected=%d",
                    pages, len(rows), affected,
                )

        logger.info(
            "UserSyncService: sync_all complete | total=%d pages=%d", total, pages
        )
        return {"synced": total, "pages": pages}

    async def get_org_stats(self) -> dict[str, Any]:
        """Return basic stats about the synced org_users table."""
        async with _session() as session:
            from src.domain.repositories.org_user_repo import OrgUserRepository
            repo = OrgUserRepository(session)
            count = await repo.count()
            departments = await repo.list_departments()
        return {"total_users": count, "departments": departments}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_user(graph_user: dict) -> dict:
        return {
            "aad_object_id": graph_user["id"],
            "display_name": graph_user.get("displayName"),
            "email": graph_user.get("mail"),
            "department": graph_user.get("department"),
            "job_title": graph_user.get("jobTitle"),
            "manager_aad_id": None,
            "manager_email": None,
        }

    async def _attach_managers(
        self, rows: list[dict], page: list[dict]
    ) -> list[dict]:
        """Enrich rows with manager info (best-effort — errors are skipped)."""
        import asyncio

        aad_ids = [u["id"] for u in page]

        async def fetch_manager(aad_id: str) -> tuple[str, dict | None]:
            try:
                mgr = await asyncio.get_event_loop().run_in_executor(
                    None, self._client.get_manager, aad_id
                )
                return aad_id, mgr
            except Exception:
                return aad_id, None

        results = await asyncio.gather(*[fetch_manager(i) for i in aad_ids])
        mgr_map = {aad_id: mgr for aad_id, mgr in results if mgr}

        for row in rows:
            mgr = mgr_map.get(row["aad_object_id"])
            if mgr:
                row["manager_aad_id"] = mgr.get("id")
                row["manager_email"] = mgr.get("mail")

        return rows
