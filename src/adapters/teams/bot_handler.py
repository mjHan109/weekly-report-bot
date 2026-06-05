"""
WeeklyReportBot — BotFrameworkAdapter setup and activity dispatch.

Responsibilities
----------------
1. Process on_message_activity: strip @mention, route to CommandRouter.
2. Handle task/fetch invokes: dispatch to the correct Task Module builder.
3. Handle task/submit invokes: dispatch to the correct Task Module submit handler.
4. Handle Adaptive Card action invokes (Action.Execute / Action.Submit).
5. Identity is ALWAYS taken from activity.from_.aad_object_id — never from
   card payload data.

Design notes
------------
- CloudAdapter (botbuilder-integration-aiohttp) is instantiated once and
  shared; the app-level route passes the raw Request object here.
- All ACL checks live inside individual handlers/task-module classes, not here.
- This class never sends personal DMs; all proactive messages go through
  CardSender.proactive_send() which targets the team channel.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes

from src.adapters.teams.command_router import CommandRouter
from src.adapters.teams.task_module.report_form import ReportFormModule
from src.adapters.teams.task_module.reporter_select_form import ReporterSelectFormModule

logger = logging.getLogger(__name__)

# Teams invoke names
INVOKE_TASK_FETCH = "task/fetch"
INVOKE_TASK_SUBMIT = "task/submit"

# Adaptive Card action invokes
INVOKE_CARD_ACTION = "adaptiveCard/action"

# Task module IDs — matched against value.data.taskModuleId in the invoke payload
TASK_MODULE_REPORT_FORM = "reportForm"
TASK_MODULE_REPORTER_SELECT = "reporterSelect"


class WeeklyReportBot(ActivityHandler):
    """Main bot entry-point wired to BotFrameworkAdapter."""

    def __init__(self) -> None:
        super().__init__()
        self._router = CommandRouter()
        self._report_form = ReportFormModule()
        self._reporter_select = ReporterSelectFormModule()

    # ------------------------------------------------------------------
    # ActivityHandler overrides
    # ------------------------------------------------------------------

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Strip @mention noise, then route to CommandRouter."""
        activity = turn_context.activity

        # Ensure identity comes from AAD, not spoofable card data
        aad_id: Optional[str] = _extract_aad_id(activity)
        if not aad_id:
            logger.warning("on_message_activity: missing aad_object_id — ignoring")
            return

        # Persist ConversationReference for proactive messaging (scheduler jobs)
        await _save_conversation_reference(turn_context)

        # Strip the bot's own @mention from the text so command matching is clean
        clean_text = _strip_at_mention(activity.text or "")
        turn_context.activity.text = clean_text

        matched = await self._router.route(turn_context)
        if not matched:
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    text=CommandRouter.help_text(),
                )
            )

    async def on_invoke_activity(self, turn_context: TurnContext) -> Any:
        """Dispatch task/fetch, task/submit and Adaptive Card action invokes."""
        invoke_name: str = turn_context.activity.name or ""

        if invoke_name == INVOKE_TASK_FETCH:
            return await self._handle_task_fetch(turn_context)

        if invoke_name == INVOKE_TASK_SUBMIT:
            return await self._handle_task_submit(turn_context)

        if invoke_name == INVOKE_CARD_ACTION:
            return await self._handle_card_action(turn_context)

        logger.debug("Unhandled invoke: %s", invoke_name)
        return _invoke_response(200, {})

    # ------------------------------------------------------------------
    # task/fetch
    # ------------------------------------------------------------------

    async def _handle_task_fetch(self, turn_context: TurnContext) -> Dict:
        """
        Build and return the Task Module payload for a given taskModuleId.

        The caller's AAD identity is resolved here and passed into the
        builder so it can be embedded as a hidden field — never taken from
        the payload itself.
        """
        activity = turn_context.activity
        aad_id = _extract_aad_id(activity)
        channel_id = _extract_channel_id(activity)
        value: Dict = activity.value or {}
        data: Dict = value.get("data", {})
        task_module_id: str = data.get("taskModuleId", "")

        logger.info(
            "task/fetch | taskModuleId=%s | aad_id=%s | channel_id=%s",
            task_module_id,
            aad_id,
            channel_id,
        )

        if task_module_id == TASK_MODULE_REPORT_FORM:
            payload = await self._report_form.build_fetch_payload(
                turn_context=turn_context,
                aad_id=aad_id,
                channel_id=channel_id,
            )
        elif task_module_id == TASK_MODULE_REPORTER_SELECT:
            payload = await self._reporter_select.build_fetch_payload(
                turn_context=turn_context,
                aad_id=aad_id,
                channel_id=channel_id,
            )
        else:
            logger.warning("task/fetch: unknown taskModuleId=%s", task_module_id)
            payload = _error_task_payload("알 수 없는 Task Module ID입니다.")

        return _invoke_response(200, payload)

    # ------------------------------------------------------------------
    # task/submit
    # ------------------------------------------------------------------

    async def _handle_task_submit(self, turn_context: TurnContext) -> Dict:
        """
        Route the submitted Task Module data to the correct handler.

        Security: submitter identity is re-verified from the activity AAD id,
        NOT from any field inside the submitted data object.
        """
        activity = turn_context.activity
        # Re-read identity from the activity — not from submitted form data
        aad_id = _extract_aad_id(activity)
        value: Dict = activity.value or {}
        data: Dict = value.get("data", {})
        task_module_id: str = data.get("taskModuleId", "")

        logger.info(
            "task/submit | taskModuleId=%s | aad_id=%s",
            task_module_id,
            aad_id,
        )

        if task_module_id == TASK_MODULE_REPORT_FORM:
            result = await self._report_form.handle_submit(
                turn_context=turn_context,
                aad_id=aad_id,
                submitted_data=data,
            )
        elif task_module_id == TASK_MODULE_REPORTER_SELECT:
            result = await self._reporter_select.handle_submit(
                turn_context=turn_context,
                aad_id=aad_id,
                submitted_data=data,
            )
        else:
            logger.warning("task/submit: unknown taskModuleId=%s", task_module_id)
            result = None  # close the task module silently

        # Returning None closes the Task Module without a follow-up card.
        # Returning a task payload would chain to a new Task Module view.
        if result:
            return _invoke_response(200, result)
        return _invoke_response(200, {})

    # ------------------------------------------------------------------
    # adaptiveCard/action
    # ------------------------------------------------------------------

    async def _handle_card_action(self, turn_context: TurnContext) -> Dict:
        """
        Handle Action.Execute (Universal Actions) from Adaptive Cards.

        Supported verbs:
          - openReportForm   : opens the report Task Module
          - openReporterSelect : opens the reporter-selection Task Module
          - triggerAggregate : team-lead triggers LLM aggregation
          - approveMail      : team-lead approves mail send
        """
        activity = turn_context.activity
        aad_id = _extract_aad_id(activity)
        value: Dict = activity.value or {}
        action: Dict = value.get("action", {})
        verb: str = action.get("verb", "")
        action_data: Dict = action.get("data", {})

        logger.info(
            "adaptiveCard/action | verb=%s | aad_id=%s", verb, aad_id
        )

        if verb == "openReportForm":
            # Redirect to task/fetch flow by returning a task continue response
            channel_id = _extract_channel_id(activity)
            payload = await self._report_form.build_fetch_payload(
                turn_context=turn_context,
                aad_id=aad_id,
                channel_id=channel_id,
            )
            return _invoke_response(200, payload)

        if verb == "openReporterSelect":
            channel_id = _extract_channel_id(activity)
            payload = await self._reporter_select.build_fetch_payload(
                turn_context=turn_context,
                aad_id=aad_id,
                channel_id=channel_id,
            )
            return _invoke_response(200, payload)

        if verb in ("triggerAggregate", "approveMail"):
            # Delegate to aggregate handler; it re-verifies team-lead ACL
            from src.adapters.teams.handlers.aggregate_report import AggregateReportHandler
            handler = AggregateReportHandler()
            await handler.handle_card_action(
                turn_context=turn_context,
                aad_id=aad_id,
                verb=verb,
                action_data=action_data,
            )
            return _invoke_response(200, {"statusCode": 200})

        logger.warning("adaptiveCard/action: unhandled verb=%s", verb)
        return _invoke_response(200, {"statusCode": 200})


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_aad_id(activity: Activity) -> Optional[str]:
    """Return the caller's AAD object ID — the only trusted identity source."""
    from_account = getattr(activity, "from_", None)
    if from_account is None:
        return None
    return getattr(from_account, "aad_object_id", None)


def _extract_channel_id(activity: Activity) -> Optional[str]:
    """
    Return the Teams channel ID from the conversation reference.

    For channel messages this is the conversation.id.
    For personal-scope messages this is also conversation.id but we treat
    channel-scope as the authoritative context for all business operations.
    """
    conversation = getattr(activity, "conversation", None)
    if conversation is None:
        return None
    return getattr(conversation, "id", None)


def _strip_at_mention(text: str) -> str:
    """Remove <at>BotName</at> tags that Teams prepends to channel messages."""
    return re.sub(r"<at>[^<]*</at>", "", text).strip()


def _invoke_response(status: int, body: Any) -> Dict:
    """Wrap a response body in the Bot Framework invoke response envelope."""
    return {"status": status, "body": body}


def _error_task_payload(message: str) -> Dict:
    """Return a minimal Task Module error card payload."""
    return {
        "task": {
            "type": "message",
            "value": message,
        }
    }


async def _save_conversation_reference(turn_context: TurnContext) -> None:
    """Persist the ConversationReference so notification_jobs can send proactive messages."""
    channel_id = _extract_channel_id(turn_context.activity)
    if not channel_id:
        return
    try:
        ref = TurnContext.get_conversation_reference(turn_context.activity)
        from src.services.reports.channel_config_service import ChannelConfigService
        await ChannelConfigService().set_conversation_reference(channel_id, ref)
    except Exception as exc:
        logger.warning("_save_conversation_reference failed channel=%s: %s", channel_id, exc)
