"""
Block Kit builder — all reporters submitted notification to team lead.

Posted to the channel when the last reporter submits their report.
"""

from __future__ import annotations


def build_all_submitted_message(channel_id: str) -> dict:
    """Channel message notifying that all reporters have submitted."""
    return {
        "text": "모든 팀원이 보고를 제출했습니다. 팀장님, 취합을 진행해 주세요.",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "✅ 전원 보고 완료"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "모든 팀원이 이번 주 보고를 제출했습니다.\n팀장님, 아래 버튼으로 취합을 진행해 주세요.",
                },
            },
            {
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
            },
        ],
    }
