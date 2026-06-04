"""Prompt template package for LLM-based report generation."""

from .personal_report import PERSONAL_REPORT_SYSTEM, build_personal_report_user
from .team_aggregate import TEAM_AGGREGATE_SYSTEM, build_team_aggregate_user
from .mail_body import MAIL_BODY_SYSTEM, build_mail_body_user

__all__ = [
    "PERSONAL_REPORT_SYSTEM",
    "build_personal_report_user",
    "TEAM_AGGREGATE_SYSTEM",
    "build_team_aggregate_user",
    "MAIL_BODY_SYSTEM",
    "build_mail_body_user",
]
