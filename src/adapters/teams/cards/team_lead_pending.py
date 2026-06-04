"""
TeamLeadPendingCard — State 1 team-lead status card.

Displayed when at least one designated reporter has not yet submitted.

Contents
--------
- Count of pending reporters with their names
- Warning: 메일 발송 불가 (mail cannot be sent)
- Action button: "취합 상태 새로고침" (re-check — triggers same verb)

This card is updated in-place via update_card(activity_id) when the
submission state changes.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_team_lead_pending_card(
    pending_names: List[str],
    channel_id: str,
    report_week: str = "",
) -> Dict[str, Any]:
    """
    Build the team-lead pending-state Adaptive Card.

    Parameters
    ----------
    pending_names : display names of reporters who have NOT yet submitted
    channel_id    : channel context (passed back in action data)
    report_week   : ISO week string, e.g. "2026-W23"
    """
    count = len(pending_names)
    names_str = ", ".join(pending_names) if pending_names else "(없음)"

    week_label = f" — {report_week}" if report_week else ""

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": f"주간 보고 현황{week_label}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"미제출: {count}명",
                "weight": "Bolder",
                "color": "Attention",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"미제출자: {names_str}",
                "wrap": True,
                "color": "Attention",
            },
            {
                "type": "TextBlock",
                "text": "전원 제출 전까지 메일 발송이 불가합니다.",
                "wrap": True,
                "isSubtle": True,
                "spacing": "Medium",
            },
        ],
        "actions": [
            {
                "type": "Action.Execute",
                "title": "취합 상태 새로고침",
                "verb": "triggerAggregate",
                "data": {
                    "channel_id": channel_id,
                },
            }
        ],
    }
