"""
Deadline1300Card — Thursday 13:00 deadline alert posted to team channel.

Behaviour rules
---------------
- Posted as a proactive channel message (not a DM) by the scheduler.
- If all submitted: informs team lead that auto-aggregation is starting.
- If pending exists: lists non-submitters and allows late self-submission.
  The team lead does NOT submit on behalf of others (ADR-006).
- @mentions pending reporters so they are notified.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_deadline_1300_card(
    pending_reporter_mentions: List[Dict[str, str]],
    submitted_count: int,
    total_count: int,
    channel_id: str,
    report_week: str = "",
) -> Dict[str, Any]:
    """
    Build the Thu 13:00 deadline alert card.

    Parameters
    ----------
    pending_reporter_mentions : reporters who have NOT submitted (for @mention)
    submitted_count           : number who did submit on time
    total_count               : total designated reporters
    channel_id                : channel context
    report_week               : ISO week string
    """
    week_label = f" ({report_week})" if report_week else ""
    all_submitted = len(pending_reporter_mentions) == 0

    # @mention entities
    mention_texts = []
    entities = []
    for reporter in pending_reporter_mentions:
        aad_id = reporter.get("aad_id", "")
        display_name = reporter.get("display_name", "팀원")
        mention_texts.append(f"<at>{display_name}</at>")
        entities.append({
            "type": "mention",
            "text": f"<at>{display_name}</at>",
            "mentioned": {
                "id": aad_id,
                "name": display_name,
            },
        })

    if all_submitted:
        status_text = f"전원 제출 완료 ({submitted_count}/{total_count}명) — 자동 취합을 시작합니다."
        status_color = "Good"
        detail_text = "팀장님, 취합이 완료되면 메일 승인 카드가 표시됩니다."
    else:
        mention_str = ", ".join(mention_texts)
        status_text = (
            f"마감 도달 — 미제출 {len(pending_reporter_mentions)}명 "
            f"({submitted_count}/{total_count}명 제출)"
        )
        status_color = "Attention"
        detail_text = (
            f"{mention_str} — 지금이라도 보고서를 제출해 주세요. "
            "전원 제출 전까지 메일 발송이 불가합니다."
        )

    body = [
        {
            "type": "TextBlock",
            "text": f"주간 보고 마감{week_label}",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": status_text,
            "weight": "Bolder",
            "color": status_color,
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": detail_text,
            "wrap": True,
            "spacing": "Medium",
        },
    ]

    actions = []
    if not all_submitted:
        # Late self-submit button for pending reporters
        actions.append({
            "type": "Action.Submit",
            "title": "지각 제출하기",
            "data": {
                "type": "task/fetch",
                "data": {
                    "taskModuleId": "reportForm",
                    "channelId": channel_id,
                    "isLate": True,
                },
            },
        })

    card: Dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    if entities:
        card["msteams"] = {"entities": entities}

    return card
