"""
CommandRouter — maps Korean bot command strings to their handler instances.

Matching is done after stripping leading/trailing whitespace from the
activity text. Partial-prefix matching is NOT used; the full canonical
command string must be present somewhere in the message text to avoid
false positives from natural conversation.

Supported commands
------------------
이번 주 보고 작성   → WriteReportHandler
팀 주간 보고 취합   → AggregateReportHandler
보고 대상 지정      → AssignReportersHandler
팀장 등록           → RegisterTeamLeadHandler
"""

from __future__ import annotations

import logging
from typing import Optional

from botbuilder.core import TurnContext

from src.adapters.teams.handlers.write_report import WriteReportHandler
from src.adapters.teams.handlers.aggregate_report import AggregateReportHandler
from src.adapters.teams.handlers.assign_reporters import AssignReportersHandler
from src.adapters.teams.handlers.register_team_lead import RegisterTeamLeadHandler

logger = logging.getLogger(__name__)

# Canonical command strings (lowercase-normalised for matching).
CMD_WRITE_REPORT = "이번 주 보고 작성"
CMD_AGGREGATE = "팀 주간 보고 취합"
CMD_ASSIGN_REPORTERS = "보고 대상 지정"
CMD_REGISTER_LEAD = "팀장 등록"


class CommandRouter:
    """Stateless router; one instance shared across the bot lifetime."""

    def __init__(self) -> None:
        self._write_report = WriteReportHandler()
        self._aggregate = AggregateReportHandler()
        self._assign_reporters = AssignReportersHandler()
        self._register_lead = RegisterTeamLeadHandler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(self, turn_context: TurnContext) -> bool:
        """
        Inspect activity text and dispatch to the matching handler.

        Returns True when a command was matched and handled, False when
        the text does not match any known command (caller may send a
        help/fallback reply).
        """
        raw_text: Optional[str] = turn_context.activity.text
        if not raw_text:
            return False

        text = raw_text.strip()

        if CMD_WRITE_REPORT in text:
            logger.info("Routing to WriteReportHandler")
            await self._write_report.handle(turn_context)
            return True

        if CMD_AGGREGATE in text:
            logger.info("Routing to AggregateReportHandler")
            await self._aggregate.handle(turn_context)
            return True

        if CMD_ASSIGN_REPORTERS in text:
            logger.info("Routing to AssignReportersHandler")
            await self._assign_reporters.handle(turn_context)
            return True

        if CMD_REGISTER_LEAD in text:
            logger.info("Routing to RegisterTeamLeadHandler")
            await self._register_lead.handle(turn_context)
            return True

        return False

    # ------------------------------------------------------------------
    # Help text for unrecognised commands
    # ------------------------------------------------------------------

    @staticmethod
    def help_text() -> str:
        return (
            "사용 가능한 명령어:\n"
            f"- `{CMD_WRITE_REPORT}` : 이번 주 보고서를 작성합니다.\n"
            f"- `{CMD_AGGREGATE}` : 팀원 보고를 취합합니다. (팀장 전용)\n"
            f"- `{CMD_ASSIGN_REPORTERS}` : 보고 대상자를 지정합니다. (팀장 전용)\n"
            f"- `{CMD_REGISTER_LEAD}` : 현재 채널의 팀장을 등록합니다.\n"
        )
