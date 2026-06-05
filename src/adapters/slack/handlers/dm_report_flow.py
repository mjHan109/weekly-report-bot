"""
Conversational DM-based weekly report flow.

State machine per user (stored in-memory):
  idle
    → [빠른 작성]          → step_done
    → [지난주 불러오기]    → step_confirm (pre-filled)
    → [취소]               → idle

  step_done       user types 완료한 업무  → step_inprogress
  step_inprogress user types 진행 중 업무 → step_plan
  step_plan       user types 다음 주 계획 → step_confirm

  step_confirm    [제출] → saved + done
                  [수정] → step_done (re-enter with existing content shown)
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory state: {user_id: State}
# State keys: step, channel_id, is_late, data
# ---------------------------------------------------------------------------

_state: dict[str, dict] = {}

STEPS = ("step_done", "step_inprogress", "step_plan", "step_confirm")

STEP_PROMPTS = {
    "step_done": (
        "✅ *완료한 업무*를 입력해주세요.\n\n"
        "_예) 1. 업무명\\n- 세부 내용_"
    ),
    "step_inprogress": (
        "🔄 *진행 중인 업무*를 입력해주세요.\n\n"
        "_없으면 `없음` 이라고 입력하세요._"
    ),
    "step_plan": (
        "📅 *다음 주 계획*을 입력해주세요.\n\n"
        "_없으면 `없음` 이라고 입력하세요._"
    ),
}

STEP_KEYS = {
    "step_done": "완료한 업무",
    "step_inprogress": "진행 중인 업무",
    "step_plan": "다음 주 계획",
}

NEXT_STEP = {
    "step_done": "step_inprogress",
    "step_inprogress": "step_plan",
    "step_plan": "step_confirm",
}


def get_state(user_id: str) -> dict | None:
    return _state.get(user_id)


def _set_state(user_id: str, step: str, channel_id: str, is_late: bool, data: dict) -> None:
    _state[user_id] = {
        "step": step,
        "channel_id": channel_id,
        "is_late": is_late,
        "data": data,
    }


def clear_state(user_id: str) -> None:
    _state.pop(user_id, None)


def set_state(user_id: str, step: str, channel_id: str, is_late: bool, data: dict) -> None:
    _set_state(user_id, step, channel_id, is_late, data)


# ---------------------------------------------------------------------------
# Entry points (called from slash command / button actions)
# ---------------------------------------------------------------------------

async def send_report_menu(user_id: str, channel_id: str, is_late: bool, client) -> None:
    """Open DM and show the initial menu buttons.

    If a DRAFT report exists for this week, shows [이어쓰기] as the first option.
    """
    dm = await client.conversations_open(users=user_id)
    dm_channel = dm["channel"]["id"]

    late_note = " ⚠️ _(마감 후 제출)_" if is_late else ""
    value = json.dumps({"channel_id": channel_id, "is_late": is_late})

    # Check for an existing DRAFT in DB
    has_draft = False
    try:
        from src.services.reports.report_service import ReportService
        draft_info = await ReportService().get_draft_report(user_id, channel_id)
        has_draft = draft_info is not None
    except Exception:
        pass

    draft_notice = (
        "\n\n📌 _작성 중인 보고서가 있습니다. [이어쓰기]로 계속하세요._"
        if has_draft else ""
    )

    buttons = []
    if has_draft:
        buttons.append({
            "type": "button",
            "action_id": "resume_draft_write",
            "text": {"type": "plain_text", "text": "이어쓰기"},
            "style": "primary",
            "value": value,
        })
    buttons += [
        {
            "type": "button",
            "action_id": "quick_write_start",
            "text": {"type": "plain_text", "text": "새로 작성" if has_draft else "빠른 작성"},
            "style": "primary" if not has_draft else "danger",
            "value": value,
        },
        {
            "type": "button",
            "action_id": "load_last_week_dm",
            "text": {"type": "plain_text", "text": "지난주 보고 불러오기"},
            "value": value,
        },
        {
            "type": "button",
            "action_id": "quick_write_cancel",
            "text": {"type": "plain_text", "text": "취소"},
            "value": value,
        },
    ]

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 *주간 보고 작성*{late_note}{draft_notice}\n\n작성 방식을 선택하세요.",
                },
            },
            {"type": "actions", "elements": buttons},
        ],
        text="주간 보고 작성",
    )


async def resume_draft(user_id: str, dm_channel: str, channel_id: str, is_late: bool, client) -> None:
    """Load existing DRAFT content from DB and jump to preview step."""
    try:
        from src.services.reports.report_service import ReportService
        draft_info = await ReportService().get_draft_report(user_id, channel_id)
        if draft_info and draft_info.get("content"):
            data = _parse_content_sections(draft_info["content"])
            _set_state(user_id, "step_confirm", channel_id, is_late, data)
            await _send_preview(user_id, dm_channel, data, channel_id, is_late, client)
            return
    except Exception as exc:
        logger.warning("resume_draft failed: %s — starting fresh", exc)

    # Fallback to fresh start if draft load fails
    await start_quick_write(user_id, dm_channel, channel_id, is_late, client)


async def start_quick_write(user_id: str, dm_channel: str, channel_id: str, is_late: bool, client) -> None:
    """Start conversational flow from the first step."""
    _set_state(user_id, "step_done", channel_id, is_late, {})

    # Create empty DRAFT in DB for persistence across server restarts
    try:
        from src.services.reports.report_service import ReportService
        await ReportService().save_draft(user_id, channel_id, "", client=client)
    except Exception as exc:
        logger.warning("save_draft on start failed (non-fatal): %s", exc)

    await client.chat_postMessage(
        channel=dm_channel,
        text=STEP_PROMPTS["step_done"],
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": STEP_PROMPTS["step_done"]},
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "1 / 3단계"}],
            },
        ],
    )


async def load_last_week_and_confirm(
    user_id: str, dm_channel: str, channel_id: str, is_late: bool, client
) -> None:
    """Load last week's report and jump straight to the confirmation step."""
    from src.adapters.slack.handlers.write_report_template import _fetch_last_week_report

    content = await _fetch_last_week_report(user_id, channel_id)
    if not content:
        await client.chat_postMessage(
            channel=dm_channel,
            text="지난주 제출한 보고서가 없습니다. 빠른 작성으로 새로 작성해주세요.",
        )
        return

    data = _parse_content_sections(content)
    _set_state(user_id, "step_confirm", channel_id, is_late, data)
    await _send_preview(user_id, dm_channel, data, channel_id, is_late, client)


# ---------------------------------------------------------------------------
# DM message router — called from handle_dm_message event handler
# ---------------------------------------------------------------------------

async def handle_dm_step(user_id: str, dm_channel: str, text: str, client) -> bool:
    """
    Route incoming DM text to the current step handler.
    Returns True if the message was consumed by the flow.
    """
    state = get_state(user_id)
    if not state:
        return False

    step = state["step"]
    if step == "step_confirm":
        # Waiting for button clicks, not text — ignore
        return True

    if step not in STEP_KEYS:
        return False

    # Save the input
    key = STEP_KEYS[step]
    state["data"][key] = text.strip()

    next_step = NEXT_STEP[step]
    state["step"] = next_step

    channel_id = state["channel_id"]
    is_late = state["is_late"]

    # Persist partial content to DB as DRAFT
    try:
        from src.services.reports.report_service import ReportService
        partial_content = (
            f"[완료한 업무]\n{state['data'].get('완료한 업무', '')}\n\n"
            f"[진행 중인 업무]\n{state['data'].get('진행 중인 업무', '')}\n\n"
            f"[다음 주 계획]\n{state['data'].get('다음 주 계획', '')}"
        )
        await ReportService().save_draft(user_id, channel_id, partial_content)
    except Exception as exc:
        logger.debug("step DRAFT save failed (non-fatal): %s", exc)

    if next_step == "step_confirm":
        await _send_preview(user_id, dm_channel, state["data"], channel_id, is_late, client)
    else:
        step_num = STEPS.index(next_step) + 1
        await client.chat_postMessage(
            channel=dm_channel,
            text=STEP_PROMPTS[next_step],
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": STEP_PROMPTS[next_step]},
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"{step_num} / 3단계"}],
                },
            ],
        )

    return True


# ---------------------------------------------------------------------------
# Preview & submit
# ---------------------------------------------------------------------------

async def _send_preview(
    user_id: str,
    dm_channel: str,
    data: dict,
    channel_id: str,
    is_late: bool,
    client,
) -> None:
    done = data.get("완료한 업무", "(없음)")
    inprog = data.get("진행 중인 업무", "(없음)")
    plan = data.get("다음 주 계획", "(없음)")

    preview_text = (
        f"*✅ 완료한 업무*\n{done}\n\n"
        f"*🔄 진행 중인 업무*\n{inprog}\n\n"
        f"*📅 다음 주 계획*\n{plan}"
    )

    payload = json.dumps({
        "channel_id": channel_id,
        "is_late": is_late,
        "data": data,
    })

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📋 *주간 보고 미리보기*\n\n{preview_text}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "dm_report_submit",
                        "text": {"type": "plain_text", "text": "제출"},
                        "style": "primary",
                        "value": payload,
                    },
                    {
                        "type": "button",
                        "action_id": "dm_report_edit",
                        "text": {"type": "plain_text", "text": "수정"},
                        "value": payload,
                    },
                ],
            },
        ],
        text="주간 보고 미리보기",
    )


async def submit_report(user_id: str, dm_channel: str, payload: dict, client) -> None:
    """Save the report and post confirmation."""
    channel_id = payload["channel_id"]
    is_late = payload["is_late"]
    data = payload["data"]

    content = (
        f"[완료한 업무]\n{data.get('완료한 업무', '')}\n\n"
        f"[진행 중인 업무]\n{data.get('진행 중인 업무', '')}\n\n"
        f"[다음 주 계획]\n{data.get('다음 주 계획', '')}"
    )

    from src.services.reports.report_service import ReportService
    await ReportService().submit_report(
        user_id=user_id, channel_id=channel_id, content=content, is_late=is_late,
    )
    clear_state(user_id)

    await client.chat_postMessage(
        channel=dm_channel,
        text="✅ *주간 보고가 제출되었습니다!*",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "✅ *주간 보고가 제출되었습니다!*"},
            }
        ],
    )

    from src.adapters.slack.blocks.personal_preview import build_submission_confirmation
    await client.chat_postMessage(
        channel=channel_id,
        **build_submission_confirmation(user_id=user_id, is_late=is_late),
    )

    from src.services.reports.report_service import ReportService as RS
    pending = await RS().get_pending_reporter_mentions(channel_id)
    if not pending:
        from src.adapters.slack.blocks.team_lead_all_submitted import build_all_submitted_message
        await client.chat_postMessage(channel=channel_id, **build_all_submitted_message(channel_id))

    logger.info("DM report submitted | user=%s | channel=%s", user_id, channel_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_content_sections(content: str) -> dict:
    sections = {"완료한 업무": "", "진행 중인 업무": "", "다음 주 계획": ""}
    current = None
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip("[] \t")
        if stripped in sections:
            if current and lines:
                sections[current] = "\n".join(lines).strip()
            current = stripped
            lines = []
        elif current:
            lines.append(line)
    if current and lines:
        sections[current] = "\n".join(lines).strip()
    return sections
