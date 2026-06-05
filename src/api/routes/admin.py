"""
Admin API routes.

POST /admin/sync-users
    Trigger a full Azure AD user sync into the org_users table.
    Requires SCHEDULER_HMAC_SECRET header (same secret as scheduler).

GET /admin/org-stats
    Return total user count and department list.

GET /admin/users/search?q=...
    Search org_users by name or email.

GET /admin/users/departments
    List all department names in the org_users table.

GET /admin/users/by-department?dept=...
    Return all users in a department (for mail recipient selection).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infra.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_bearer = HTTPBearer()


def _verify_secret(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """Verify the shared HMAC secret used by the scheduler."""
    settings = get_settings()
    if creds.credentials != settings.scheduler_hmac_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

@router.post("/sync-users", dependencies=[Depends(_verify_secret)])
async def sync_users(fetch_managers: bool = False) -> dict:
    """Trigger a full Azure AD → org_users sync.

    Parameters
    ----------
    fetch_managers:
        Also fetch each user's manager (requires Directory.Read.All).
        Significantly more API calls — use with caution on large tenants.
    """
    from src.services.graph.user_sync_service import UserSyncService
    try:
        result = await UserSyncService().sync_all(fetch_managers=fetch_managers)
        return {"ok": True, **result}
    except Exception as exc:
        logger.error("sync_users failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------

@router.get("/org-stats")
async def org_stats() -> dict:
    """Return total user count and department list."""
    from src.services.graph.user_sync_service import UserSyncService
    return await UserSyncService().get_org_stats()


@router.get("/users/search")
async def search_users(q: str = Query(..., min_length=1)) -> list[dict]:
    """Search org_users by display_name or email (partial, case-insensitive)."""
    from src.infra.db import _get_session_factory
    from src.domain.repositories.org_user_repo import OrgUserRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    factory = _get_session_factory()
    async with factory() as session:
        repo = OrgUserRepository(session)
        users = await repo.search(q, limit=20)
        return [
            {
                "aad_object_id": u.aad_object_id,
                "display_name": u.display_name,
                "email": u.email,
                "department": u.department,
                "job_title": u.job_title,
            }
            for u in users
        ]


@router.get("/users/departments")
async def list_departments() -> list[str]:
    """Return distinct department names."""
    from src.infra.db import _get_session_factory
    from src.domain.repositories.org_user_repo import OrgUserRepository

    factory = _get_session_factory()
    async with factory() as session:
        repo = OrgUserRepository(session)
        return await repo.list_departments()


@router.get("/users/by-department")
async def users_by_department(dept: str = Query(..., min_length=1)) -> list[dict]:
    """Return all users in a department."""
    from src.infra.db import _get_session_factory
    from src.domain.repositories.org_user_repo import OrgUserRepository

    factory = _get_session_factory()
    async with factory() as session:
        repo = OrgUserRepository(session)
        users = await repo.get_by_department(dept)
        return [
            {
                "aad_object_id": u.aad_object_id,
                "display_name": u.display_name,
                "email": u.email,
                "job_title": u.job_title,
                "manager_email": u.manager_email,
            }
            for u in users
        ]
