"""
Block Kit builders for personal report flow:
  - write_report_modal  : report submission form (Modal)
  - assign_reporters_modal : reporter assignment form (Modal)
  - build_submission_confirmation : post-submit channel message
"""

from __future__ import annotations


def build_write_report_modal(channel_id: str, is_late: bool, existing: dict | None = None) -> dict:
    """Build the report writing Modal view payload with 3 separate fields."""
    title = "주간 보고 수정" if existing else "주간 보고 작성"
    ex = existing or {}

    def _input(block_id, action_id, label, placeholder, key):
        el = {
            "type": "plain_text_input",
            "action_id": action_id,
            "multiline": True,
            "placeholder": {"type": "plain_text", "text": placeholder},
        }
        if ex.get(key):
            el["initial_value"] = ex[key]
        return {"block_id": block_id, "type": "input", "label": {"type": "plain_text", "text": label}, "element": el}

    blocks = [
        _input("done_block", "done_input", "✅  완료한 업무",
               "1. 업무명\n    - 세부 내용\n2. 업무명\n    - 세부 내용", "완료한 업무"),
        _input("inprogress_block", "inprogress_input", "🔄  진행 중인 업무",
               "1. 업무명\n    - 세부 내용", "진행 중인 업무"),
        _input("plan_block", "plan_input", "📅  다음 주 계획",
               "1. 업무명\n2. 업무명", "다음 주 계획"),
    ]

    if is_late:
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "⚠️ 마감(13:00)이 지난 지각 제출입니다."}
            ],
        })

    return {
        "type": "modal",
        "callback_id": "write_report_modal",
        "private_metadata": f"{channel_id}|{'true' if is_late else 'false'}",
        "title": {"type": "plain_text", "text": title},
        "submit": {"type": "plain_text", "text": "제출"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": blocks,
    }


def build_assign_reporters_modal(channel_id: str) -> dict:
    """Build the reporter assignment Modal view payload."""
    return {
        "type": "modal",
        "callback_id": "assign_reporters_modal",
        "private_metadata": channel_id,
        "title": {"type": "plain_text", "text": "보고 대상자 지정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "이 채널에서 주간 보고를 제출할 팀원을 선택하세요.",
                },
            },
            {
                "block_id": "reporters_block",
                "type": "input",
                "label": {"type": "plain_text", "text": "보고 대상자"},
                "element": {
                    "type": "multi_users_select",
                    "action_id": "reporters_select",
                    "placeholder": {"type": "plain_text", "text": "팀원 선택"},
                },
            },
        ],
    }


def build_submission_confirmation(user_id: str, is_late: bool) -> dict:
    """Channel message confirming a report was submitted."""
    text = f"<@{user_id}> 님이 이번 주 보고를 제출했습니다."
    if is_late:
        text += " _(지각 제출)_"

    return {
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ {text}"},
            }
        ],
    }
