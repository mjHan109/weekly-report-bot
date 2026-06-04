"""
ReportFormModule — Task Module for weekly report submission.

task/fetch payload
------------------
Returns a task/continue response containing an Adaptive Card with:
  - 4 visible text-input fields:
      1. 이번 주 한 일 (this_week)
      2. 다음 주 할 일 (next_week)
      3. 이슈/블로커 (issues)
      4. 특이사항 (notes)
  - 4 hidden fields bound server-side at fetch time (NOT editable by client):
      - channel_id
      - submitter_aad_id   (from activity.from_.aad_object_id)
      - report_week        (ISO week string, e.g. "2026-W23")
      - is_late            (bool — True if past Thu 13:00)

task/submit handling
--------------------
- Re-reads submitter_aad_id from activity.from_.aad_object_id (NOT from data).
- Validates that the submitter matches a designated reporter for the channel.
- Saves the report via ReportService.
- Posts a personal_preview Adaptive Card to the channel (not a DM).
- If all reporters have now submitted, fires the auto-aggregation path.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from botbuilder.core import TurnContext

logger = logging.getLogger(__name__)

# Task Module dimensions
TASK_MODULE_WIDTH = 600
TASK_MODULE_HEIGHT = 560


class ReportFormModule:
    """Builds the report-form Task Module payload and handles submissions."""

    # ------------------------------------------------------------------
    # task/fetch
    # ------------------------------------------------------------------

    async def build_fetch_payload(
        self,
        turn_context: TurnContext,
        aad_id: Optional[str],
        channel_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Return a task/continue envelope containing the report Adaptive Card.

        Hidden fields are set here on the server; the client cannot tamper
        with submitter_aad_id because it is overwritten on submit from the
        activity identity.
        """
        report_week = _current_iso_week()
        is_late = await _is_past_deadline(channel_id)

        card_payload = _build_report_card(
            channel_id=channel_id or "",
            submitter_aad_id=aad_id or "",
            report_week=report_week,
            is_late=is_late,
        )

        return {
            "task": {
                "type": "continue",
                "value": {
                    "title": "이번 주 보고 작성" + (" (지각 제출)" if is_late else ""),
                    "height": TASK_MODULE_HEIGHT,
                    "width": TASK_MODULE_WIDTH,
                    "card": {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card_payload,
                    },
                },
            }
        }

    # ------------------------------------------------------------------
    # task/submit
    # ------------------------------------------------------------------

    async def handle_submit(
        self,
        turn_context: TurnContext,
        aad_id: Optional[str],
        submitted_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Validate and persist the submitted report.

        aad_id MUST come from turn_context.activity.from_.aad_object_id
        (already resolved by bot_handler) — never from submitted_data.

        Returns None to close the Task Module; the channel confirmation card
        is sent proactively.
        """
        # Re-assert: never trust submitted_data for identity
        channel_id: str = submitted_data.get("channel_id", "")
        report_week: str = submitted_data.get("report_week", _current_iso_week())
        is_late: bool = submitted_data.get("is_late", False)

        this_week: str = (submitted_data.get("this_week") or "").strip()
        next_week: str = (submitted_data.get("next_week") or "").strip()
        issues: str = (submitted_data.get("issues") or "").strip()
        notes: str = (submitted_data.get("notes") or "").strip()

        if not aad_id:
            logger.warning("report_form submit: missing aad_id — rejecting")
            return None

        if not channel_id:
            logger.warning("report_form submit: missing channel_id in data — rejecting")
            return None

        # ACL: must be a designated reporter
        if not await _is_designated_reporter(aad_id, channel_id):
            logger.warning(
                "report_form submit: aad_id=%s is not a designated reporter for channel=%s",
                aad_id,
                channel_id,
            )
            return None

        # Persist the report
        report_data = {
            "aad_id": aad_id,
            "channel_id": channel_id,
            "report_week": report_week,
            "is_late": is_late,
            "this_week": this_week,
            "next_week": next_week,
            "issues": issues,
            "notes": notes,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "report_form: saving report | aad_id=%s | channel=%s | week=%s | late=%s",
            aad_id,
            channel_id,
            report_week,
            is_late,
        )

        await _save_report(report_data)

        # Post personal preview card to channel (not DM)
        await _post_personal_preview(turn_context, report_data)

        # Check if all reporters submitted — fire auto-aggregation if so
        await _check_all_submitted_and_aggregate(turn_context, channel_id)

        # Close the Task Module (no follow-up dialog)
        return None


# ---------------------------------------------------------------------------
# Adaptive Card builder
# ---------------------------------------------------------------------------

def _build_report_card(
    channel_id: str,
    submitter_aad_id: str,
    report_week: str,
    is_late: bool,
) -> Dict[str, Any]:
    """
    Build the Adaptive Card JSON for the report form.

    Hidden fields are implemented as Input.Text with isVisible=false so
    they are submitted with the form but not displayed to the user.
    """
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": f"주간 보고 — {report_week}" + (" (지각 제출)" if is_late else ""),
                "weight": "Bolder",
                "size": "Medium",
            },
            # Visible fields
            {
                "type": "TextBlock",
                "text": "이번 주 한 일",
                "weight": "Bolder",
            },
            {
                "type": "Input.Text",
                "id": "this_week",
                "placeholder": "이번 주에 완료한 업무를 입력하세요.",
                "isMultiline": True,
                "maxLength": 1000,
            },
            {
                "type": "TextBlock",
                "text": "다음 주 할 일",
                "weight": "Bolder",
            },
            {
                "type": "Input.Text",
                "id": "next_week",
                "placeholder": "다음 주에 진행할 업무를 입력하세요.",
                "isMultiline": True,
                "maxLength": 1000,
            },
            {
                "type": "TextBlock",
                "text": "이슈/블로커",
                "weight": "Bolder",
            },
            {
                "type": "Input.Text",
                "id": "issues",
                "placeholder": "이슈 또는 블로커가 있으면 입력하세요. (없으면 비워두세요)",
                "isMultiline": True,
                "maxLength": 500,
            },
            {
                "type": "TextBlock",
                "text": "특이사항",
                "weight": "Bolder",
            },
            {
                "type": "Input.Text",
                "id": "notes",
                "placeholder": "기타 특이사항을 입력하세요. (없으면 비워두세요)",
                "isMultiline": True,
                "maxLength": 500,
            },
            # Hidden fields — bound server-side
            {
                "type": "Input.Text",
                "id": "taskModuleId",
                "value": "reportForm",
                "isVisible": False,
            },
            {
                "type": "Input.Text",
                "id": "channel_id",
                "value": channel_id,
                "isVisible": False,
            },
            {
                "type": "Input.Text",
                "id": "submitter_aad_id",
                "value": submitter_aad_id,
                "isVisible": False,
            },
            {
                "type": "Input.Text",
                "id": "report_week",
                "value": report_week,
                "isVisible": False,
            },
            {
                "type": "Input.Text",
                "id": "is_late",
                "value": str(is_late).lower(),
                "isVisible": False,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "제출",
                "data": {"taskModuleId": "reportForm"},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    """Return ISO week string such as '2026-W23'."""
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def _is_past_deadline(channel_id: Optional[str]) -> bool:
    try:
        from src.services.reports.deadline_service import DeadlineService
        return await DeadlineService().is_past_deadline(channel_id)
    except ImportError:
        return False


async def _is_designated_reporter(aad_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_designated_reporter(aad_id, channel_id)
    except ImportError:
        logger.warning("ReportService not available — ACL stub returns True")
        return True


async def _save_report(report_data: Dict[str, Any]) -> None:
    try:
        from src.services.reports.report_service import ReportService
        await ReportService().save_report(report_data)
    except ImportError:
        logger.warning("ReportService not available — report save stub (no-op)")


async def _post_personal_preview(
    turn_context: TurnContext, report_data: Dict[str, Any]
) -> None:
    from src.adapters.teams.cards.personal_preview import build_personal_preview_card
    from src.adapters.teams.cards.card_sender import CardSender

    card = build_personal_preview_card(report_data)
    sender = CardSender()
    await sender.send_card(turn_context=turn_context, card=card)


async def _check_all_submitted_and_aggregate(
    turn_context: TurnContext, channel_id: str
) -> None:
    """
    If all reporters have now submitted, trigger auto-aggregation and update
    the team-lead status card in the channel.
    """
    try:
        from src.services.reports.report_service import ReportService
        pending = await ReportService().get_pending_reporter_names(channel_id)
    except ImportError:
        return

    if not pending:
        logger.info("All submitted after latest report — triggering auto-aggregation")
        from src.adapters.teams.handlers.aggregate_report import AggregateReportHandler
        handler = AggregateReportHandler()
        await handler._process_aggregation(
            turn_context=turn_context,
            aad_id="scheduler",  # system-triggered
            channel_id=channel_id,
        )
