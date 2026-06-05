"""
Block Kit builder — aggregate preview message.

Posted after LLM aggregation is complete. Shows the draft
aggregated report and provides a "메일 발송" button.
"""

from __future__ import annotations


def build_aggregate_preview_message(
    aggregated_text: str,
    draft_id: str,
    report_week: str,
) -> dict:
    """Channel message showing the aggregated weekly report with a draft review button."""
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
                        "action_id": "mail_draft_open",
                        "text": {"type": "plain_text", "text": "📧 메일 초안 보기"},
                        "style": "primary",
                        "value": draft_id,
                    }
                ],
            },
        ],
    }
