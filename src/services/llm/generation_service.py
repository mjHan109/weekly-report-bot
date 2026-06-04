"""High-level async functions for LLM-based report generation.

All public functions are async and use the module-level default LLMClient.
They accept domain model objects defined in src/models/ (PersonalReport,
ChannelConfig) — or plain dicts during early development — and return
formatted Korean strings ready for email assembly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .client import LLMClient, get_default_client
from .prompts.personal_report import (
    PERSONAL_REPORT_SYSTEM,
    build_personal_report_user,
)
from .prompts.team_aggregate import (
    TEAM_AGGREGATE_SYSTEM,
    build_team_aggregate_user,
)
from .prompts.mail_body import (
    MAIL_BODY_SYSTEM,
    build_mail_body_user,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight domain models (used until shared models/ package is ready)
# ---------------------------------------------------------------------------


@dataclass
class PersonalReport:
    """Individual weekly report submitted by a team member."""

    name: str                        # 제출자 이름
    week_period: str                 # e.g. "2026-06-01 ~ 2026-06-05"
    this_week: str                   # 이번 주 한 일
    next_week: str                   # 다음 주 할 일
    issues: str = ""                 # 이슈 / 블로커
    notes: str = ""                  # 특이사항
    is_late: bool = False            # 목요일 13:00 이후 제출 여부


@dataclass
class ChannelConfig:
    """Per-channel configuration for report aggregation."""

    team_name: str                           # 팀/채널 표시 이름
    week_period: str                         # e.g. "2026-06-01 ~ 2026-06-05"
    to_recipients: list[str] = field(default_factory=list)   # 수신자 목록
    cc_recipients: list[str] = field(default_factory=list)   # 참조 목록


# ---------------------------------------------------------------------------
# Token budgets
# ---------------------------------------------------------------------------

_PERSONAL_MAX_TOKENS = 512
_AGGREGATE_MAX_TOKENS = 2048
_MAIL_MAX_TOKENS = 1024
_TEMPERATURE = 0.3

# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def generate_personal_summary(
    report: PersonalReport,
    client: Optional[LLMClient] = None,
) -> str:
    """Format a single PersonalReport into a clean Korean report section.

    Args:
        report: The individual weekly report data.
        client: Optional LLMClient override; defaults to the module-level client.

    Returns:
        Formatted Korean report text (100–200 chars per section).
    """
    llm = client or get_default_client()
    user_prompt = build_personal_report_user(
        name=report.name,
        week_period=report.week_period,
        this_week=report.this_week,
        next_week=report.next_week,
        issues=report.issues,
        notes=report.notes,
        is_late=report.is_late,
    )
    logger.info("Generating personal summary for '%s' (late=%s).", report.name, report.is_late)
    result = await llm.complete_async(
        system=PERSONAL_REPORT_SYSTEM,
        user=user_prompt,
        max_tokens=_PERSONAL_MAX_TOKENS,
        temperature=_TEMPERATURE,
    )
    logger.debug("Personal summary generated for '%s': %d chars.", report.name, len(result))
    return result


async def generate_team_aggregate(
    reports: list[PersonalReport],
    channel_config: ChannelConfig,
    client: Optional[LLMClient] = None,
) -> str:
    """Aggregate multiple PersonalReports into a team-level Korean weekly report.

    Steps:
    1. Generate individual summaries in parallel.
    2. Pass all summaries into the team aggregate prompt.

    Args:
        reports: List of individual weekly reports for the team.
        channel_config: Team/channel metadata (name, week period).
        client: Optional LLMClient override; defaults to the module-level client.

    Returns:
        Formatted Korean team aggregate report (~1500 chars).
    """
    import asyncio

    llm = client or get_default_client()

    # Step 1: generate personal summaries in parallel
    logger.info(
        "Generating %d personal summaries for team '%s'.",
        len(reports),
        channel_config.team_name,
    )
    personal_summaries: list[str] = await asyncio.gather(
        *[generate_personal_summary(r, llm) for r in reports]
    )

    # Step 2: build individual_reports list for team prompt
    individual_reports: list[tuple[str, str, bool]] = [
        (r.name, summary, r.is_late)
        for r, summary in zip(reports, personal_summaries)
    ]

    user_prompt = build_team_aggregate_user(
        team_name=channel_config.team_name,
        week_period=channel_config.week_period,
        individual_reports=individual_reports,
    )

    logger.info("Generating team aggregate for '%s'.", channel_config.team_name)
    result = await llm.complete_async(
        system=TEAM_AGGREGATE_SYSTEM,
        user=user_prompt,
        max_tokens=_AGGREGATE_MAX_TOKENS,
        temperature=_TEMPERATURE,
    )
    logger.debug(
        "Team aggregate generated for '%s': %d chars.", channel_config.team_name, len(result)
    )
    return result


async def generate_mail_body(
    aggregate_content: str,
    channel_config: ChannelConfig,
    client: Optional[LLMClient] = None,
) -> str:
    """Format an aggregated report as a professional Korean email body.

    Args:
        aggregate_content: Output from generate_team_aggregate().
        channel_config: Team/channel metadata including recipient lists.
        client: Optional LLMClient override; defaults to the module-level client.

    Returns:
        Complete Korean email body string with greeting and sign-off.
    """
    llm = client or get_default_client()
    user_prompt = build_mail_body_user(
        team_name=channel_config.team_name,
        week_period=channel_config.week_period,
        aggregate_content=aggregate_content,
        to_recipients=channel_config.to_recipients,
        cc_recipients=channel_config.cc_recipients,
    )
    logger.info("Generating mail body for team '%s'.", channel_config.team_name)
    result = await llm.complete_async(
        system=MAIL_BODY_SYSTEM,
        user=user_prompt,
        max_tokens=_MAIL_MAX_TOKENS,
        temperature=_TEMPERATURE,
    )
    logger.debug("Mail body generated: %d chars.", len(result))
    return result
