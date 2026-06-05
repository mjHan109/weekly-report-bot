"""
Block Kit builder — team lead pending status card.

Shown to the team lead when some reporters haven't submitted yet.
Includes a "직접 취합" button to force aggregation anyway.
"""

from __future__ import annotations


def build_team_lead_pending_message(
    channel_id: str,
    pending_user_ids: list[str],
) -> dict:
    """Ephemeral message shown to team lead listing pending reporters."""
    if pending_user_ids:
        names = "\n".join(f"• <@{uid}>" for uid in pending_user_ids)
        status_text = f"*미제출자 ({len(pending_user_ids)}명):*\n{names}"
    else:
        status_text = "모든 팀원이 보고를 제출했습니다."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "주간 보고 현황"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": status_text},
        },
    ]

    if pending_user_ids:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "aggregate_confirm",
                    "text": {"type": "plain_text", "text": "직접 취합하기"},
                    "style": "primary",
                    "value": channel_id,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "취합 확인"},
                        "text": {
                            "type": "mrkdwn",
                            "text": f"미제출자 {len(pending_user_ids)}명이 있습니다. 지금 취합하시겠습니까?",
                        },
                        "confirm": {"type": "plain_text", "text": "취합"},
                        "deny": {"type": "plain_text", "text": "취소"},
                    },
                }
            ],
        })
    else:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "aggregate_confirm",
                    "text": {"type": "plain_text", "text": "취합 및 메일 작성"},
                    "style": "primary",
                    "value": channel_id,
                }
            ],
        })

    return {"text": "주간 보고 현황", "blocks": blocks}
