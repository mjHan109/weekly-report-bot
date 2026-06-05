"""MailSettings — per-channel report schedule and email configuration.

All settings are per Slack channel. Team leads manage them via /설정.

Template variables available in greeting / closing / mail_subject_format:
    {sender_name}   — team lead's display name
    {team_name}     — team name (free text)
    {month}         — current month (숫자)
    {week}          — week-of-month (숫자)
    {week_key}      — ISO week key e.g. "2026-W23"
    {year}          — 4-digit year
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.models.base import Base, TimestampMixin


class MailSettings(Base, TimestampMixin):
    """Per-channel schedule, template, and mail settings."""

    __tablename__ = "mail_settings"

    channel_id: Mapped[str] = mapped_column(String(256), primary_key=True)

    # ── Team / sender info ────────────────────────────────────────────────────
    team_name: Mapped[str] = mapped_column(String(128), default="개발팀", nullable=False)
    sender_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    # ── Deadline schedule ─────────────────────────────────────────────────────
    # deadline_weekday: 0=월 1=화 2=수 3=목 4=금 5=토 6=일  (default 3=목)
    deadline_weekday: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # deadline_hour: 0–23 KST  (default 13)
    deadline_hour: Mapped[int] = mapped_column(Integer, default=13, nullable=False)

    # ── Reminder schedule ─────────────────────────────────────────────────────
    # Comma-separated hours before deadline to send reminders, e.g. "3,1"
    # Empty string = no reminders
    reminder_hours: Mapped[str] = mapped_column(String(64), default="3,1", nullable=False)

    # ── Report template ───────────────────────────────────────────────────────
    # Shown as pre-filled text when user starts a new report
    report_template: Mapped[str] = mapped_column(
        Text,
        default=(
            "[완료한 업무]\n"
            "1. \n\n"
            "[진행 중인 업무]\n"
            "1. \n\n"
            "[다음 주 계획]\n"
            "1. "
        ),
        nullable=False,
    )

    # ── Email templates ───────────────────────────────────────────────────────
    greeting: Mapped[str] = mapped_column(
        Text,
        default=(
            "안녕하세요.\n"
            "{team_name} {sender_name}입니다.\n"
            "{month}월 {week}주차 팀 주간보고 송부 드립니다."
        ),
        nullable=False,
    )
    closing: Mapped[str] = mapped_column(
        Text,
        default="오늘 하루도 고생하셨습니다.\n{sender_name} 올림.",
        nullable=False,
    )

    # Subject format — supports same template variables
    mail_subject_format: Mapped[str] = mapped_column(
        String(256),
        default="[주간보고] {year}년 {month}월 {week}주차 {team_name} 주간보고서",
        nullable=False,
    )

    # ── Recipients ────────────────────────────────────────────────────────────
    # Comma-separated email addresses
    default_mail_to: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_mail_cc: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Whether to automatically add the team lead to CC
    auto_cc_team_lead: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def reminder_hours_list(self) -> list[int]:
        """Parse reminder_hours into a list of ints. Empty list if disabled."""
        if not self.reminder_hours.strip():
            return []
        result = []
        for part in self.reminder_hours.split(","):
            try:
                result.append(int(part.strip()))
            except ValueError:
                pass
        return result

    def render_subject(self, week_key: str) -> str:
        """Render mail_subject_format with current date context."""
        import datetime
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        month = today.month
        # week-of-month: approximate using ISO week
        week_of_month = ((iso_week - 1) % 4) + 1
        return self.mail_subject_format.format(
            team_name=self.team_name,
            sender_name=self.sender_name,
            year=iso_year,
            month=month,
            week=week_of_month,
            week_key=week_key,
        )
