"""
AggregationService — weekly report aggregation (no LLM required).

Fetches submitted personal reports for the current week and formats
them into a professional Korean weekly report.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db import _get_session_factory
from src.services.reports.week_utils import current_week_key

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


def _week_period() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return f"{monday.strftime('%Y년 %m월 %d일')} ~ {friday.strftime('%m월 %d일')}"


def _parse_sections(content: str) -> dict[str, str]:
    """Parse report content into section dict."""
    sections = {"완료한 업무": "", "진행 중인 업무": "", "다음 주 계획": ""}
    current = None
    lines: list[str] = []

    for line in content.splitlines():
        stripped = line.strip("[] \t")
        if stripped in sections:
            if current and lines:
                sections[current] = "\n".join(lines).strip()
            current = stripped
            lines = []
        elif current:
            lines.append(line)

    if current and lines:
        sections[current] = "\n".join(lines).strip()

    return sections


def _indent_subitems(text: str) -> str:
    """Convert dash sub-items (indented or plain `- `) to bullet prefix."""
    import re
    result = []
    for line in text.splitlines():
        if re.match(r"^ {2,}- ", line) or line.startswith("- "):
            line = re.sub(r"^( {2,})?- ", "  • ", line)
        result.append(line)
    return "\n".join(result)


def _number_top_level(text: str) -> str:
    """Bold already-numbered top-level items (N. text).
    Plain `- item` lines are treated as sub-items, not renumbered.
    If a section has NO numbered lines, convert `- item` to numbered.
    """
    import re
    has_numbered = bool(re.search(r"^\d+\. ", text, re.MULTILINE))
    result = []
    counter = 1
    for line in text.splitlines():
        if m := re.match(r"^(\d+)\. (.+)", line):
            result.append(f"{m.group(1)}. *{m.group(2)}*")
            counter += 1
        elif not has_numbered and line.startswith("- "):
            result.append(f"{counter}. *{line[2:]}*")
            counter += 1
        else:
            result.append(line)
    return "\n".join(result)


class AggregationService:

    async def aggregate_weekly_reports(
        self,
        channel_id: str,
        slack_client=None,
    ) -> str:
        """
        Fetch all submitted reports and format into a professional report.
        slack_client: optional Slack WebClient for fetching display names.
        """
        week_key = current_week_key()

        try:
            async with _session() as session:
                from src.domain.repositories.personal_report_repo import PersonalReportRepository
                from src.domain.repositories.channel_config_repo import ChannelConfigRepository
                from src.domain.enums import ReportStatus

                report_repo = PersonalReportRepository(session)
                config_repo = ChannelConfigRepository(session)

                reports = await report_repo.list_for_week(channel_id, week_key)
                submitted = [
                    r for r in reports
                    if r.status in (ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED)
                ]

                targets = await config_repo.get_active_targets(channel_id)
                name_map = {
                    t.aad_object_id: t.display_name
                    for t in targets
                    if t.display_name
                }

        except Exception as exc:
            logger.error("aggregate_weekly_reports DB error: %s", exc)
            return "*(보고서를 불러오는 중 오류가 발생했습니다)*"

        if not submitted:
            return "*(제출된 보고서가 없습니다)*"

        # Fetch missing display names from Slack
        if slack_client:
            for report in submitted:
                if report.aad_object_id not in name_map:
                    try:
                        resp = await slack_client.users_info(user=report.aad_object_id)
                        profile = resp["user"]["profile"]
                        name_map[report.aad_object_id] = (
                            profile.get("display_name")
                            or profile.get("real_name")
                            or report.aad_object_id
                        )
                    except Exception:
                        pass

        week_period = _week_period()
        lines = [
            f"_{week_period}_",
            f"제출 인원: {len(submitted)}명",
            "",
        ]

        for i, report in enumerate(submitted, 1):
            name = name_map.get(report.aad_object_id, report.aad_object_id)
            lines.append(f"👤 *{name}*")

            sections = _parse_sections(report.content or "")

            if sections["완료한 업무"]:
                lines.append(f"▪ 완료한 업무\n{_indent_subitems(_number_top_level(sections['완료한 업무']))}")
            if sections["진행 중인 업무"]:
                lines.append(f"▪ 진행 중인 업무\n{_indent_subitems(_number_top_level(sections['진행 중인 업무']))}")
            if sections["다음 주 계획"]:
                lines.append(f"▪ 다음 주 계획\n{_indent_subitems(_number_top_level(sections['다음 주 계획']))}")

            if i < len(submitted):
                lines.append("─" * 20)

        return "\n".join(lines)

    def format_for_email(self, aggregated: str, team_name: str = "개발팀") -> str:
        """Wrap aggregated content in a professional Korean email body."""
        week_key = current_week_key()
        today = date.today()
        month = today.month
        # Calculate week-of-month (roughly)
        week_of_month = (today.day - 1) // 7 + 1

        return (
            f"안녕하세요.\n\n"
            f"{team_name} {month}월 {week_of_month}주차 주간 보고 드립니다.\n\n"
            f"{'─' * 40}\n\n"
            f"{aggregated}\n\n"
            f"{'─' * 40}\n\n"
            f"수고하셨습니다.\n"
            f"{team_name} 드림"
        )
