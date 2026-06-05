"""
Block Kit builder — Thursday 10:00 reminder card.

Posted proactively to the channel at 10:00 KST on report day.
@mentions all reporters who haven't submitted yet.
"""

from __future__ import annotations


def build_reminder_1000_message(
    pending_user_ids: list[str],
    channel_id: str,
    report_week: str,
) -> dict:
    """Channel reminder message listing reporters who haven't submitted."""
    if pending_user_ids:
        mentions = " ".join(f"<@{uid}>" for uid in pending_user_ids)
        body = (
            f"{mentions}\n"
            f"오늘 *13:00* 까지 주간 보고를 제출해 주세요.\n"
            f"`/주간보고` 명령어를 사용하세요."
        )
    else:
        body = "모든 팀원이 이미 보고를 제출했습니다. 수고하셨습니다! 🎉"

    return {
        "text": f"[{report_week}] 주간 보고 제출 안내 (10:00)",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📢 주간 보고 제출 안내"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"보고 기간: {report_week} | 마감: 오늘 13:00",
                    }
                ],
            },
        ],
    }
