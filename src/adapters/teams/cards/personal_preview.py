"""
PersonalPreviewCard — shown in the team channel after a reporter submits.

This card is NOT a DM. It is posted to the team channel so the team lead
can see who has submitted and review the content at a glance.

Card contents
-------------
- Reporter display name and submission timestamp
- Summary of the four report fields
- "지각 제출" badge if is_late is True
"""

from __future__ import annotations

from typing import Any, Dict


def build_personal_preview_card(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the personal-preview Adaptive Card payload.

    Parameters
    ----------
    report_data : dict with keys:
        aad_id, channel_id, report_week, is_late,
        this_week, next_week, issues, notes,
        submitted_at, display_name (optional)
    """
    display_name: str = report_data.get("display_name") or "팀원"
    report_week: str = report_data.get("report_week", "")
    is_late: bool = bool(report_data.get("is_late", False))
    submitted_at: str = report_data.get("submitted_at", "")

    this_week: str = report_data.get("this_week") or "(없음)"
    next_week: str = report_data.get("next_week") or "(없음)"
    issues: str = report_data.get("issues") or "(없음)"
    notes: str = report_data.get("notes") or "(없음)"

    title_suffix = " — 지각 제출" if is_late else ""
    submitted_label = f"제출 시각: {submitted_at}" if submitted_at else ""

    body = [
        {
            "type": "TextBlock",
            "text": f"[{report_week}] {display_name}님 보고 제출{title_suffix}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Attention" if is_late else "Default",
        },
    ]

    if submitted_label:
        body.append({
            "type": "TextBlock",
            "text": submitted_label,
            "size": "Small",
            "isSubtle": True,
        })

    body.extend([
        {"type": "TextBlock", "text": "이번 주 한 일", "weight": "Bolder", "spacing": "Medium"},
        {"type": "TextBlock", "text": this_week, "wrap": True},
        {"type": "TextBlock", "text": "다음 주 할 일", "weight": "Bolder", "spacing": "Medium"},
        {"type": "TextBlock", "text": next_week, "wrap": True},
        {"type": "TextBlock", "text": "이슈/블로커", "weight": "Bolder", "spacing": "Medium"},
        {"type": "TextBlock", "text": issues, "wrap": True},
        {"type": "TextBlock", "text": "특이사항", "weight": "Bolder", "spacing": "Medium"},
        {"type": "TextBlock", "text": notes, "wrap": True},
    ])

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
