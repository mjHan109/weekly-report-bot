"""
Block Kit builders for personal report flow:
  - write_report_modal  : report submission form (Modal)
  - assign_reporters_modal : reporter assignment form (Modal)
  - build_submission_confirmation : post-submit channel message
"""

from __future__ import annotations


def build_write_report_modal(channel_id: str, is_late: bool) -> dict:
    """Build the report writing Modal view payload."""
    title = "이번 주 보고 작성"
    if is_late:
        title += " (지각)"

    return {
        "type": "modal",
        "callback_id": "write_report_modal",
        "private_metadata": f"{channel_id}|{'true' if is_late else 'false'}",
        "title": {"type": "plain_text", "text": title},
        "submit": {"type": "plain_text", "text": "제출"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*이번 주 업무 내용을 입력하세요.*\n"
                        "• 완료한 업무\n"
                        "• 진행 중인 업무\n"
                        "• 다음 주 계획"
                        + ("\n\n⚠️ *마감(13:00)이 지난 지각 제출입니다.*" if is_late else "")
                    ),
                },
            },
            {
                "block_id": "report_block",
                "type": "input",
                "label": {"type": "plain_text", "text": "보고 내용"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "report_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "이번 주 업무 내용을 작성하세요...",
                    },
                },
            },
        ],
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
