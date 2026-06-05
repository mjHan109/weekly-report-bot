"""
Block Kit builder — email draft preview.

Shows To, CC, Subject, body preview with Edit / Send / Cancel buttons.
Posted to channel after team lead opens the draft.
"""

from __future__ import annotations

from src.adapters.slack.draft_store import MailDraft


def build_mail_draft_preview(draft: MailDraft) -> dict:
    body_preview = draft.mail_body[:600] + ("..." if len(draft.mail_body) > 600 else "")
    cc_text = draft.mail_cc if draft.mail_cc else "(없음)"

    return {
        "text": "📧 메일 초안 확인",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📧 메일 초안"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*수신자*\n{draft.mail_to}"},
                    {"type": "mrkdwn", "text": f"*참조*\n{cc_text}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*제목*\n{draft.mail_subject}"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*본문 미리보기*\n```{body_preview}```",
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "mail_draft_edit",
                        "text": {"type": "plain_text", "text": "✏️ 수정"},
                        "value": draft.draft_id,
                    },
                    {
                        "type": "button",
                        "action_id": "mail_draft_send",
                        "text": {"type": "plain_text", "text": "📤 발송"},
                        "style": "primary",
                        "value": draft.draft_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "메일 발송 확인"},
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{draft.mail_to}* 에게 메일을 발송하시겠습니까?",
                            },
                            "confirm": {"type": "plain_text", "text": "발송"},
                            "deny": {"type": "plain_text", "text": "취소"},
                        },
                    },
                    {
                        "type": "button",
                        "action_id": "mail_draft_cancel",
                        "text": {"type": "plain_text", "text": "🗑️ 발송 취소"},
                        "style": "danger",
                        "value": draft.draft_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "취소 확인"},
                            "text": {
                                "type": "mrkdwn",
                                "text": "메일 발송을 취소하시겠습니까?",
                            },
                            "confirm": {"type": "plain_text", "text": "취소"},
                            "deny": {"type": "plain_text", "text": "아니오"},
                        },
                    },
                ],
            },
        ],
    }
