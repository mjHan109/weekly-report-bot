"""AuditLogRepository — append-only insert for AuditLog rows."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.audit_log import AuditLog


class AuditLogRepository:
    """Write-only repository for the audit_logs table.

    All rows are immutable once written — no update or delete methods.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        event_type: str,
        actor_aad_id: str,
        *,
        channel_id: str | None = None,
        week_key: str | None = None,
        personal_report_id: int | None = None,
        team_report_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Insert one audit log row and flush (does not commit).

        Args:
            event_type:         Dot-namespaced verb, e.g. "report.submit".
            actor_aad_id:       AAD object ID of the acting user, or "system".
            channel_id:         Slack / Teams channel ID (optional).
            week_key:           ISO week key "YYYY-WNN" (optional).
            personal_report_id: FK to personal_reports.id (optional).
            team_report_id:     FK to team_reports.id (optional).
            payload:            Extra event-specific data (serialised to JSON).
        """
        row = AuditLog(
            event_type=event_type,
            actor_aad_id=actor_aad_id,
            channel_id=channel_id,
            week_key=week_key,
            personal_report_id=personal_report_id,
            team_report_id=team_report_id,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_recent(
        self,
        channel_id: str,
        *,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Return recent audit log rows for a channel, newest first."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.channel_id == channel_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        if event_type:
            stmt = stmt.where(AuditLog.event_type == event_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
