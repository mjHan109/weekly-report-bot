"""
Block Kit builder — Thursday 13:00 deadline card.

Posted proactively at the deadline. Shows submission counts and
any remaining pending reporters.
"""

from __future__ import annotations


def build_deadline_1300_message(
    pending_user_ids: list[str],
    submitted_count: int,
    total_count: int,
    channel_id: str,
    report_week: str,
) -> dict:
    """Channel message at 13:00 deadline showing submission status."""
    if not pending_user_ids:
        body = f"*전원 제출 완료!* ({submitted_count}/{total_count})\n자동으로 취합을 시작합니다..."
        emoji = "✅"
    else:
        mentions = " ".join(f"<@{uid}>" for uid in pending_user_ids)
        body = (
            f"마감 시간이 지났습니다.\n"
            f"*제출 현황:* {submitted_count}/{total_count}\n"
            f"*미제출:* {mentions}\n\n"
            f"미제출자는 지금 `/주간보고` 로 지각 제출할 수 있습니다."
        )
        emoji = "⏰"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} 주간 보고 마감 ({report_week})"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body},
        },
    ]

    if pending_user_ids:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "aggregate_confirm",
                    "text": {"type": "plain_text", "text": "지금 취합하기"},
                    "style": "primary",
                    "value": channel_id,
                }
            ],
        })

    return {
        "text": f"[{report_week}] 주간 보고 마감 — {submitted_count}/{total_count} 제출",
        "blocks": blocks,
    }
