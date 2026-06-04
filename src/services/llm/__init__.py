"""LLM service package for weekly report generation."""

from .client import LLMClient
from .generation_service import generate_personal_summary, generate_team_aggregate, generate_mail_body

__all__ = [
    "LLMClient",
    "generate_personal_summary",
    "generate_team_aggregate",
    "generate_mail_body",
]
