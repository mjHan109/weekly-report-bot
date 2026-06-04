"""
AggregateReportHandler — "팀 주간 보고 취합" command.

ACL rules
---------
- The invoking user MUST be the registered team lead for this channel.
- Identity is taken from activity.from_.aad_object_id only.

Aggregation modes (ADR-003)
---------------------------
A. Auto-aggregation (all submitted before 13:00 Thu)
   - Triggered automatically by the scheduler; this handler is the manual
     fallback path used when late submitters have filed.
B. Manual aggregation (at least one missing at deadline)
   - Team lead runs "팀 주간 보고 취합" after all late self-submits are done.
   - OR team lead clicks the "취합하기" button on the team_lead_all_submitted card.

Flow
----
  Team lead types "팀 주간 보고 취합"
    -> ACL: must be team lead
    -> Check submission state
       - Still pending → send team_lead_pending card (or update existing)
       - All submitted  → trigger LLM aggregation → send aggregate_preview card
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes

logger = logging.getLogger(__name__)


class AggregateReportHandler:
    """Handles the '팀 주간 보고 취합' command and card action verbs."""

    async def handle(self, turn_context: TurnContext) -> None:
        aad_id = _get_aad_id(turn_context)
        channel_id = _get_channel_id(turn_context)

        if not aad_id or not channel_id:
            await _reply(turn_context, "사용자 또는 채널 정보를 확인할 수 없습니다.")
            return

        # ACL: team lead only
        if not await _is_team_lead(aad_id, channel_id):
            await _reply(turn_context, "팀장만 사용할 수 있는 명령어입니다.")
            return

        await self._process_aggregation(turn_context, aad_id, channel_id)

    async def handle_card_action(
        self,
        turn_context: TurnContext,
        aad_id: str,
        verb: str,
        action_data: Dict[str, Any],
    ) -> None:
        """
        Handle Adaptive Card action verbs: triggerAggregate, approveMail.

        Identity is already validated by bot_handler before this is called,
        but we re-check team-lead ACL here as a second gate.
        """
        channel_id = _get_channel_id(turn_context)
        if not channel_id:
            return

        if not await _is_team_lead(aad_id, channel_id):
            logger.warning(
                "Card action '%s' rejected — not team lead | aad_id=%s",
                verb,
                aad_id,
            )
            return

        if verb == "triggerAggregate":
            await self._process_aggregation(turn_context, aad_id, channel_id)
        elif verb == "approveMail":
            await self._approve_and_send_mail(turn_context, aad_id, channel_id, action_data)

    # ------------------------------------------------------------------
    # Internal aggregation logic
    # ------------------------------------------------------------------

    async def _process_aggregation(
        self,
        turn_context: TurnContext,
        aad_id: str,
        channel_id: str,
    ) -> None:
        from src.adapters.teams.cards.card_sender import CardSender
        from src.adapters.teams.cards.team_lead_pending import build_team_lead_pending_card
        from src.adapters.teams.cards.team_lead_all_submitted import build_team_lead_all_submitted_card
        from src.adapters.teams.cards.aggregate_preview import build_aggregate_preview_card

        sender = CardSender()
        pending_reporters = await _get_pending_reporters(channel_id)

        if pending_reporters:
            # Not all submitted — update/send pending state card
            logger.info(
                "AggregateReportHandler: %d pending | channel=%s",
                len(pending_reporters),
                channel_id,
            )
            card = build_team_lead_pending_card(
                pending_names=pending_reporters,
                channel_id=channel_id,
            )
            existing_activity_id = await _get_lead_card_activity_id(channel_id)
            if existing_activity_id:
                await sender.update_card(
                    turn_context=turn_context,
                    activity_id=existing_activity_id,
                    card=card,
                    channel_id=channel_id,
                )
            else:
                new_activity_id = await sender.send_card(
                    turn_context=turn_context,
                    card=card,
                )
                await _store_lead_card_activity_id(channel_id, new_activity_id)
            await _reply(
                turn_context,
                f"아직 {len(pending_reporters)}명이 미제출입니다. 전원 제출 후 다시 시도하세요.",
            )
            return

        # All submitted — trigger LLM aggregation
        logger.info("AggregateReportHandler: all submitted — triggering LLM | channel=%s", channel_id)
        aggregated_text = await _trigger_llm_aggregation(channel_id)

        card = build_aggregate_preview_card(
            aggregated_text=aggregated_text,
            channel_id=channel_id,
        )
        existing_activity_id = await _get_lead_card_activity_id(channel_id)
        if existing_activity_id:
            await sender.update_card(
                turn_context=turn_context,
                activity_id=existing_activity_id,
                card=card,
                channel_id=channel_id,
            )
        else:
            new_activity_id = await sender.send_card(
                turn_context=turn_context,
                card=card,
            )
            await _store_lead_card_activity_id(channel_id, new_activity_id)

    async def _approve_and_send_mail(
        self,
        turn_context: TurnContext,
        aad_id: str,
        channel_id: str,
        action_data: Dict[str, Any],
    ) -> None:
        """Team lead approves the aggregated preview and triggers Graph mail send."""
        logger.info(
            "AggregateReportHandler: approveMail | aad_id=%s | channel=%s",
            aad_id,
            channel_id,
        )
        try:
            from src.services.mail.mail_service import MailService
            await MailService().send_weekly_report_mail(
                channel_id=channel_id,
                approved_by_aad_id=aad_id,
            )
            await _reply(turn_context, "주간 보고 메일이 발송되었습니다.")
        except ImportError:
            logger.warning("MailService not yet available — mail send stub")
            await _reply(turn_context, "메일 서비스를 준비 중입니다.")
        except Exception as exc:
            logger.error("Mail send failed: %s", exc)
            await _reply(turn_context, f"메일 발송 중 오류가 발생했습니다: {exc}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_aad_id(turn_context: TurnContext) -> Optional[str]:
    from_account = getattr(turn_context.activity, "from_", None)
    if from_account is None:
        return None
    return getattr(from_account, "aad_object_id", None)


def _get_channel_id(turn_context: TurnContext) -> Optional[str]:
    conversation = getattr(turn_context.activity, "conversation", None)
    if conversation is None:
        return None
    return getattr(conversation, "id", None)


async def _is_team_lead(aad_id: str, channel_id: str) -> bool:
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().is_team_lead(aad_id, channel_id)
    except ImportError:
        logger.warning("ReportService not available — team-lead ACL stub returns True")
        return True


async def _get_pending_reporters(channel_id: str) -> list[str]:
    """Return display names of reporters who have not yet submitted."""
    try:
        from src.services.reports.report_service import ReportService
        return await ReportService().get_pending_reporter_names(channel_id)
    except ImportError:
        return []


async def _trigger_llm_aggregation(channel_id: str) -> str:
    """Call the LLM service to aggregate all submitted reports for the week."""
    try:
        from src.services.llm.aggregation_service import AggregationService
        return await AggregationService().aggregate_weekly_reports(channel_id)
    except ImportError:
        logger.warning("AggregationService not available — returning placeholder text")
        return "(LLM 취합 결과 — 서비스 준비 중)"


async def _get_lead_card_activity_id(channel_id: str) -> Optional[str]:
    """Fetch the stored activity_id for the team-lead status card in this channel."""
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        return await ChannelConfigService().get_lead_card_activity_id(channel_id)
    except ImportError:
        return None


async def _store_lead_card_activity_id(channel_id: str, activity_id: Optional[str]) -> None:
    """Persist the activity_id so subsequent card updates can use update_card()."""
    if not activity_id:
        return
    try:
        from src.services.reports.channel_config_service import ChannelConfigService
        await ChannelConfigService().set_lead_card_activity_id(channel_id, activity_id)
    except ImportError:
        pass


async def _reply(turn_context: TurnContext, text: str) -> None:
    await turn_context.send_activity(
        Activity(type=ActivityTypes.message, text=text)
    )
