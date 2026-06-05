"""
Block Kit builder — email draft edit modal.

Allows team lead to modify To, CC, Subject, and body before sending.
"""

from __future__ import annotations

from src.adapters.slack.draft_store import MailDraft


def build_mail_draft_modal(draft: MailDraft, departments: list[str] | None = None) -> dict:
    """Build the email draft edit modal.

    Parameters
    ----------
    draft:
        Current draft state.
    departments:
        Optional list of department names from org_users.
        When provided, shows a department quick-fill section above the To field.
    """
    blocks = []

    # ── Department quick-fill (shown only when org_users are synced) ─────────
    if departments:
        dept_options = [
            {"text": {"type": "plain_text", "text": d}, "value": d}
            for d in departments
        ]
        blocks += [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*부서별 수신자 자동 입력*\n부서를 선택하면 해당 부서 전체 메일이 수신자에 채워집니다.",
                },
            },
            {
                "type": "actions",
                "block_id": "dept_quickfill",
                "elements": [
                    {
                        "type": "static_select",
                        "action_id": "dept_select",
                        "placeholder": {"type": "plain_text", "text": "부서 선택…"},
                        "options": dept_options,
                    }
                ],
            },
            {"type": "divider"},
        ]

    # ── Mail fields ───────────────────────────────────────────────────────────
    blocks += [
        {
            "type": "input",
            "block_id": "mail_to",
            "label": {"type": "plain_text", "text": "수신자"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "initial_value": draft.mail_to,
                "placeholder": {
                    "type": "plain_text",
                    "text": "example@company.com, example2@company.com",
                },
            },
            "hint": {
                "type": "plain_text",
                "text": "쉼표로 여러 명 입력 가능",
            },
        },
        {
            "type": "input",
            "block_id": "mail_cc",
            "optional": True,
            "label": {"type": "plain_text", "text": "참조"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "initial_value": draft.mail_cc,
                "placeholder": {
                    "type": "plain_text",
                    "text": "cc1@company.com, cc2@company.com",
                },
            },
        },
        {
            "type": "input",
            "block_id": "mail_subject",
            "label": {"type": "plain_text", "text": "제목"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "initial_value": draft.mail_subject,
            },
        },
        {
            "type": "input",
            "block_id": "mail_body",
            "label": {"type": "plain_text", "text": "본문"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "initial_value": draft.mail_body,
                "multiline": True,
            },
        },
    ]

    return {
        "type": "modal",
        "callback_id": "mail_draft_edit_modal",
        "private_metadata": draft.draft_id,
        "title": {"type": "plain_text", "text": "메일 초안 수정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": blocks,
    }
