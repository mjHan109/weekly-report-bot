"""
AggregatePreviewCard — shown after LLM aggregation is complete.

Contents
--------
- The LLM-generated aggregated report text (mail preview)
- "메일 발송 승인" action button — team lead approves and triggers Graph mail
- "다시 취합하기" action — re-trigger LLM aggregation (idempotent)

This card replaces the team_lead_all_submitted card in-place via
update_card(activity_id).
"""

from __future__ import annotations

from typing import Any, Dict


def build_aggregate_preview_card(
    aggregated_text: str,
    channel_id: str,
    report_week: str = "",
    mail_to: str = "",
) -> Dict[str, Any]:
    """
    Build the aggregate-preview Adaptive Card.

    Parameters
    ----------
    aggregated_text : LLM-generated mail body text
    channel_id      : passed back in action data
    report_week     : ISO week string
    mail_to         : recipient address shown as preview (display only)
    """
    week_label = f" — {report_week}" if report_week else ""
    recipient_label = f"수신: {mail_to}" if mail_to else ""

    body = [
        {
            "type": "TextBlock",
            "text": f"주간 보고 취합 완료{week_label}",
            "weight": "Bolder",
            "size": "Medium",
        },
    ]

    if recipient_label:
        body.append({
            "type": "TextBlock",
            "text": recipient_label,
            "isSubtle": True,
            "size": "Small",
        })

    body.extend([
        {
            "type": "TextBlock",
            "text": "메일 미리보기",
            "weight": "Bolder",
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": aggregated_text or "(취합 결과 없음)",
            "wrap": True,
            "fontType": "Monospace",
        },
        {
            "type": "TextBlock",
            "text": "내용을 확인 후 메일 발송을 승인하세요.",
            "wrap": True,
            "isSubtle": True,
            "spacing": "Medium",
        },
    ])

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [
            {
                "type": "Action.Execute",
                "title": "메일 발송 승인",
                "verb": "approveMail",
                "style": "positive",
                "data": {
                    "channel_id": channel_id,
                    "report_week": report_week,
                },
            },
            {
                "type": "Action.Execute",
                "title": "다시 취합하기",
                "verb": "triggerAggregate",
                "data": {
                    "channel_id": channel_id,
                },
            },
        ],
    }
