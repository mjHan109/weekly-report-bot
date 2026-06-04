"""Draft mail service.

Builds an Outlook draft message from a TeamReport and persists it via
GraphClient.  The draft is saved in the team lead's mailbox so they can
review it before the triple-gate send.

No direct httpx calls are made here — all Graph interactions go through
GraphClient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .graph_client import GraphClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts (minimal — align with DB models when Phase 2 DB is ready)
# ---------------------------------------------------------------------------

@dataclass
class PersonalReportSummary:
    """Summary of a single member's weekly report for mail rendering."""
    member_name: str
    member_email: str
    content: str
    submitted_at: str  # ISO-8601 string


@dataclass
class TeamReportData:
    """Aggregated team report passed to build_draft().

    Fields
    ------
    channel_id:     Teams channel ID (for logging / traceability)
    week_key:       ISO week string, e.g. "2026-W23"
    team_lead_oid:  AAD object ID of the team lead (mailbox owner)
    team_lead_email: Email address of the team lead (From / To)
    report_items:   Individual member reports in submission order
    extra_recipients: Additional To addresses beyond the team lead
    cc_recipients:  CC addresses
    """
    channel_id: str
    week_key: str
    team_lead_oid: str
    team_lead_email: str
    report_items: list[PersonalReportSummary]
    extra_recipients: list[str] = field(default_factory=list)
    cc_recipients: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Draft builder
# ---------------------------------------------------------------------------

class DraftService:
    """Builds and saves Outlook draft messages from team report data.

    Parameters
    ----------
    graph_client:
        Authenticated GraphClient instance.
    """

    def __init__(self, graph_client: GraphClient) -> None:
        self._gc = graph_client

    def build_draft(self, team_report: TeamReportData) -> dict[str, Any]:
        """Create a draft in the team lead's mailbox.

        Steps
        -----
        1. Render HTML body from *team_report*.
        2. Call GraphClient.create_draft() — delegated Mail.ReadWrite scope.
        3. Log the created message ID and return the Graph message object.

        Returns
        -------
        The Graph message dict (contains ``id`` used by send_service).
        """
        subject = self._build_subject(team_report)
        body_html = self._render_html(team_report)

        to_addresses = [team_report.team_lead_email] + team_report.extra_recipients

        logger.info(
            "DraftService: building draft oid=%s week=%s channel=%s",
            team_report.team_lead_oid,
            team_report.week_key,
            team_report.channel_id,
        )

        message = self._gc.create_draft(
            oid=team_report.team_lead_oid,
            to=to_addresses,
            cc=team_report.cc_recipients,
            subject=subject,
            body=body_html,
            body_type="HTML",
        )

        logger.info(
            "DraftService: draft saved message_id=%s oid=%s",
            message.get("id"),
            team_report.team_lead_oid,
        )
        return message

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_subject(report: TeamReportData) -> str:
        return f"[주간 보고] {report.week_key} 팀 보고서"

    @staticmethod
    def _render_html(report: TeamReportData) -> str:
        """Render a simple HTML body for the weekly report mail."""
        rows = []
        for idx, item in enumerate(report.report_items, start=1):
            rows.append(
                f"<tr>"
                f"<td style='padding:8px;border:1px solid #ddd;'>{idx}</td>"
                f"<td style='padding:8px;border:1px solid #ddd;'>{_esc(item.member_name)}</td>"
                f"<td style='padding:8px;border:1px solid #ddd;white-space:pre-wrap;'>"
                f"{_esc(item.content)}</td>"
                f"<td style='padding:8px;border:1px solid #ddd;'>{_esc(item.submitted_at)}</td>"
                f"</tr>"
            )
        table_rows = "\n".join(rows)

        return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#333;">
  <h2>{_esc(report.week_key)} 주간 팀 보고서</h2>
  <p>팀 채널 ID: {_esc(report.channel_id)}</p>
  <table style="border-collapse:collapse;width:100%;">
    <thead>
      <tr style="background:#f0f0f0;">
        <th style="padding:8px;border:1px solid #ddd;">#</th>
        <th style="padding:8px;border:1px solid #ddd;">팀원</th>
        <th style="padding:8px;border:1px solid #ddd;">내용</th>
        <th style="padding:8px;border:1px solid #ddd;">제출 시각</th>
      </tr>
    </thead>
    <tbody>
{table_rows}
    </tbody>
  </table>
  <p style="margin-top:24px;color:#888;font-size:12px;">
    본 메일은 Teams 주간 보고 자동화 시스템에서 생성되었습니다.
  </p>
</body>
</html>"""


def _esc(text: str) -> str:
    """Minimal HTML escaping for report content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
