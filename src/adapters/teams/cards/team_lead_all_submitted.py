"""
TeamLeadAllSubmittedCard — State 2 team-lead status card.

Displayed when all designated reporters have submitted and LLM aggregation
can proceed (or has just completed).

Contents
--------
- Confirmation that all N reporters have submitted
- "취합하기" action button — triggers LLM aggregation
- Used as an intermediate state before aggregate_preview card
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_team_lead_all_submitted_card(
    submitted_names: List[str],
    channel_id: str,
    report_week: str = "",
) -> Dict[str, Any]:
    """
    Build the all-submitted state card.

    Parameters
    ----------
    submitted_names : display names of all reporters who submitted
    channel_id      : passed back in action data
    report_week     : ISO week string
    """
    count = len(submitted_names)
    names_str = ", ".join(submitted_names) if submitted_names else "(없음)"
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
                "text": f"전원 제출 완료 ({count}명)",
                "weight": "Bolder",
                "color": "Good",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"제출자: {names_str}",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "아래 버튼을 눌러 취합 및 메일 작성을 시작하세요.",
                "wrap": True,
                "spacing": "Medium",
            },
        ],
        "actions": [
            {
                "type": "Action.Execute",
                "title": "취합하기",
                "verb": "triggerAggregate",
                "data": {
                    "channel_id": channel_id,
                },
            }
        ],
    }
