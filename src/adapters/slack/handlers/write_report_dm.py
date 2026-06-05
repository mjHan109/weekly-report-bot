"""
DM-based conversational report submission handler.

Flow
----
1. User clicks "대화형으로 작성" button  → bot opens DM, asks first question
2. User replies in DM (3 steps)          → bot collects answers
3. Final confirmation step               → bot shows preview + submit/cancel buttons
4. User clicks "제출"                    → report saved, confirmation posted in original channel
"""

from __future__ import annotations

import logging

from src.adapters.slack import conversation_state as cs

logger = logging.getLogger(__name__)


async def start_dm_flow(user_id: str, channel_id: str, is_late: bool, client) -> None:
    """Open a DM and ask the first question."""
    cs.start(user_id, channel_id, is_late)

    # Open DM channel
    dm = await client.conversations_open(users=user_id)
    dm_channel = dm["channel"]["id"]

    late_note = "\n\n⚠️ _마감 후 지각 제출입니다._" if is_late else ""
    await client.chat_postMessage(
        channel=dm_channel,
        text=(
            f"📝 *주간 보고 대화형 작성을 시작합니다.*{late_note}\n\n"
            + cs.STEP_PROMPTS["done"]
        ),
    )
    logger.info("DM flow started | user=%s | channel=%s", user_id, channel_id)


async def handle_dm_message(user_id: str, dm_channel: str, text: str, client) -> None:
    """Process a DM reply and advance the conversation."""
    state = cs.get(user_id)
    if not state:
        return

    current_step = state["step"]

    if current_step == "confirm":
        # Handled by button actions, ignore text
        return

    next_step = cs.save_step(user_id, text)

    if next_step == "confirm":
        await _show_preview(user_id, dm_channel, client)
    elif next_step in cs.STEP_PROMPTS:
        await client.chat_postMessage(
            channel=dm_channel,
            text=cs.STEP_PROMPTS[next_step],
        )


async def _show_preview(user_id: str, dm_channel: str, client) -> None:
    """Show the completed report preview with submit/cancel buttons."""
    state = cs.get(user_id)
    if not state:
        return

    data = state["data"]
    preview = (
        f"*[완료한 업무]*\n{data.get('완료한 업무', '(없음)')}\n\n"
        f"*[진행 중인 업무]*\n{data.get('진행 중인 업무', '(없음)')}\n\n"
        f"*[다음 주 계획]*\n{data.get('다음 주 계획', '(없음)')}"
    )

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📋 *작성 내용 확인*\n\n{preview}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "dm_submit_report",
                        "text": {"type": "plain_text", "text": "제출"},
                        "style": "primary",
                        "value": user_id,
                    },
                    {
                        "type": "button",
                        "action_id": "dm_cancel_report",
                        "text": {"type": "plain_text", "text": "취소"},
                        "style": "danger",
                        "value": user_id,
                    },
                ],
            },
        ],
        text="주간 보고 확인",
    )


async def handle_submit(user_id: str, dm_channel: str, client) -> None:
    """Submit the report and notify in the original channel."""
    state = cs.get(user_id)
    if not state:
        await client.chat_postMessage(channel=dm_channel, text="제출할 보고서가 없습니다.")
        return

    data = state["data"]
    channel_id = state["channel_id"]
    is_late = state["is_late"]
    cs.clear(user_id)

    content = (
        f"[완료한 업무]\n{data.get('완료한 업무', '')}\n\n"
        f"[진행 중인 업무]\n{data.get('진행 중인 업무', '')}\n\n"
        f"[다음 주 계획]\n{data.get('다음 주 계획', '')}"
    )

    try:
        from src.services.reports.report_service import ReportService
        await ReportService().submit_report(
            user_id=user_id,
            channel_id=channel_id,
            content=content,
            is_late=is_late,
        )
    except Exception as exc:
        logger.error("DM submit failed: %s", exc)
        await client.chat_postMessage(channel=dm_channel, text=f"❌ 제출 실패: {exc}")
        return

    await client.chat_postMessage(channel=dm_channel, text="✅ 보고서가 제출되었습니다!")

    # Notify original channel
    from src.adapters.slack.blocks.personal_preview import build_submission_confirmation
    msg = build_submission_confirmation(user_id=user_id, is_late=is_late)
    await client.chat_postMessage(channel=channel_id, **msg)

    # Check if all submitted
    try:
        from src.services.reports.report_service import ReportService
        pending = await ReportService().get_pending_reporter_mentions(channel_id)
        if not pending:
            from src.adapters.slack.blocks.team_lead_all_submitted import build_all_submitted_message
            await client.chat_postMessage(channel=channel_id, **build_all_submitted_message(channel_id))
    except Exception:
        pass

    logger.info("DM report submitted | user=%s | channel=%s", user_id, channel_id)


async def handle_cancel(user_id: str, dm_channel: str, client) -> None:
    """Cancel the DM flow."""
    cs.clear(user_id)
    await client.chat_postMessage(channel=dm_channel, text="보고서 작성을 취소했습니다.")
