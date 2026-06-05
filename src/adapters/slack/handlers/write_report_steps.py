"""
Step-by-step modal report submission.

Uses views.open / views.push / views.update to walk the user through
3 input steps without requiring DM message events.

Step flow
---------
  step1_done       → step2_inprogress → step3_plan → step4_confirm
  (완료한 업무)       (진행 중인 업무)     (다음 주 계획)  (확인 및 제출)
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _meta(channel_id: str, is_late: bool, data: dict) -> str:
    return json.dumps({"channel_id": channel_id, "is_late": is_late, "data": data})


def _parse_meta(private_metadata: str) -> tuple[str, bool, dict]:
    m = json.loads(private_metadata)
    return m["channel_id"], m["is_late"], m.get("data", {})


# ── Step views ────────────────────────────────────────────────────────────────

def _step_view(
    callback_id: str,
    title: str,
    label: str,
    placeholder: str,
    private_metadata: str,
    initial_value: str = "",
    step_indicator: str = "",
) -> dict:
    el: dict = {
        "type": "plain_text_input",
        "action_id": "step_input",
        "multiline": True,
        "placeholder": {"type": "plain_text", "text": placeholder},
    }
    if initial_value:
        el["initial_value"] = initial_value

    blocks = []
    if step_indicator:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": step_indicator}],
        })
    blocks.append({
        "block_id": "input_block",
        "type": "input",
        "label": {"type": "plain_text", "text": label},
        "element": el,
    })

    return {
        "type": "modal",
        "callback_id": callback_id,
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "주간 보고 작성"},
        "submit": {"type": "plain_text", "text": "다음"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": blocks,
    }


def build_step1(channel_id: str, is_late: bool, initial: str = "") -> dict:
    meta = _meta(channel_id, is_late, {})
    return _step_view(
        callback_id="step_done",
        title="주간 보고 작성",
        label="✅  완료한 업무",
        placeholder="1. 업무명\n    - 세부 내용\n2. 업무명\n    - 세부 내용",
        private_metadata=meta,
        initial_value=initial,
        step_indicator="1 / 3단계",
    )


def build_step2(channel_id: str, is_late: bool, data: dict, initial: str = "") -> dict:
    meta = _meta(channel_id, is_late, data)
    return _step_view(
        callback_id="step_inprogress",
        title="주간 보고 작성",
        label="🔄  진행 중인 업무",
        placeholder="1. 업무명\n    - 세부 내용",
        private_metadata=meta,
        initial_value=initial,
        step_indicator="2 / 3단계",
    )


def build_step3(channel_id: str, is_late: bool, data: dict, initial: str = "") -> dict:
    meta = _meta(channel_id, is_late, data)
    return _step_view(
        callback_id="step_plan",
        title="주간 보고 작성",
        label="📅  다음 주 계획",
        placeholder="1. 업무명\n2. 업무명",
        private_metadata=meta,
        initial_value=initial,
        step_indicator="3 / 3단계",
    )


def build_confirm(channel_id: str, is_late: bool, data: dict) -> dict:
    meta = _meta(channel_id, is_late, data)
    done = data.get("완료한 업무", "(없음)")
    inp = data.get("진행 중인 업무", "(없음)")
    plan = data.get("다음 주 계획", "(없음)")

    return {
        "type": "modal",
        "callback_id": "step_confirm",
        "private_metadata": meta,
        "title": {"type": "plain_text", "text": "보고서 확인"},
        "submit": {"type": "plain_text", "text": "제출"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*✅ 완료한 업무*\n{done}"},
                "accessory": {
                    "type": "button",
                    "action_id": "edit_step_done",
                    "text": {"type": "plain_text", "text": "✏️ 수정"},
                    "value": meta,
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*🔄 진행 중인 업무*\n{inp}"},
                "accessory": {
                    "type": "button",
                    "action_id": "edit_step_inprogress",
                    "text": {"type": "plain_text", "text": "✏️ 수정"},
                    "value": meta,
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*📅 다음 주 계획*\n{plan}"},
                "accessory": {
                    "type": "button",
                    "action_id": "edit_step_plan",
                    "text": {"type": "plain_text", "text": "✏️ 수정"},
                    "value": meta,
                },
            },
        ],
    }


# ── Handler functions ─────────────────────────────────────────────────────────

async def open_step1(trigger_id: str, channel_id: str, is_late: bool, client) -> None:
    await client.views_open(trigger_id=trigger_id, view=build_step1(channel_id, is_late))


async def on_step1_submit(ack, view: dict) -> None:
    channel_id, is_late, data = _parse_meta(view["private_metadata"])
    text = view["state"]["values"]["input_block"]["step_input"]["value"] or ""
    data["완료한 업무"] = text
    await ack(response_action="update", view=build_step2(channel_id, is_late, data))


async def on_step2_submit(ack, view: dict) -> None:
    channel_id, is_late, data = _parse_meta(view["private_metadata"])
    text = view["state"]["values"]["input_block"]["step_input"]["value"] or ""
    data["진행 중인 업무"] = text
    await ack(response_action="update", view=build_step3(channel_id, is_late, data))


async def on_step3_submit(ack, view: dict) -> None:
    channel_id, is_late, data = _parse_meta(view["private_metadata"])
    text = view["state"]["values"]["input_block"]["step_input"]["value"] or ""
    data["다음 주 계획"] = text
    await ack(response_action="update", view=build_confirm(channel_id, is_late, data))


async def on_confirm_submit(view: dict, user_id: str, client) -> None:
    channel_id, is_late, data = _parse_meta(view["private_metadata"])
    content = (
        f"[완료한 업무]\n{data.get('완료한 업무', '')}\n\n"
        f"[진행 중인 업무]\n{data.get('진행 중인 업무', '')}\n\n"
        f"[다음 주 계획]\n{data.get('다음 주 계획', '')}"
    )

    from src.services.reports.report_service import ReportService
    await ReportService().submit_report(
        user_id=user_id, channel_id=channel_id, content=content, is_late=is_late,
    )

    from src.adapters.slack.blocks.personal_preview import build_submission_confirmation
    await client.chat_postMessage(
        channel=channel_id,
        **build_submission_confirmation(user_id=user_id, is_late=is_late),
    )

    # Check all submitted
    pending = await ReportService().get_pending_reporter_mentions(channel_id)
    if not pending:
        from src.adapters.slack.blocks.team_lead_all_submitted import build_all_submitted_message
        await client.chat_postMessage(channel=channel_id, **build_all_submitted_message(channel_id))

    logger.info("Step-modal report submitted | user=%s | channel=%s", user_id, channel_id)
