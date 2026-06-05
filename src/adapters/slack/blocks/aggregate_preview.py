"""
Block Kit builder — aggregate preview message.

Posted after LLM aggregation is complete. Shows the draft
aggregated report and provides a "메일 발송" button.
"""

from __future__ import annotations


def build_aggregate_preview_message(
    aggregated_text: str,
    channel_id: str,
    report_week: str,
) -> dict:
    """Channel message showing the LLM-aggregated weekly report draft."""
    # Slack block text max is 3000 chars
    preview = aggregated_text[:2800] + ("..." if len(aggregated_text) > 2800 else "")

    return {
        "text": f"[{report_week}] 주간 보고 취합 완료",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📋 주간 보고 취합 — {report_week}"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": preview},
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "send_mail_confirm",
                        "text": {"type": "plain_text", "text": "메일 발송"},
                        "style": "primary",
                        "value": f"{channel_id}|{report_week}",
                        "confirm": {
                            "title": {"type": "plain_text", "text": "메일 발송 확인"},
                            "text": {
                                "type": "mrkdwn",
                                "text": "취합된 내용으로 메일을 발송하시겠습니까?",
                            },
                            "confirm": {"type": "plain_text", "text": "발송"},
                            "deny": {"type": "plain_text", "text": "취소"},
                        },
                    }
                ],
            },
        ],
    }
