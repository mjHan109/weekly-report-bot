"""
Reminder1000Card — Thursday 10:00 reminder posted to team channel.

Behaviour rules
---------------
- Posted as a proactive channel message (not a DM) by the scheduler.
- @mentions each pending (not-yet-submitted) reporter by their Teams user ID.
- Includes a "보고서 작성하기" button that opens the report Task Module directly.
- This card does NOT update in-place; a new message is posted each week.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_reminder_1000_card(
    pending_reporter_mentions: List[Dict[str, str]],
    channel_id: str,
    report_week: str = "",
) -> Dict[str, Any]:
    """
    Build the Thu 10:00 reminder card.

    Parameters
    ----------
    pending_reporter_mentions : list of {"aad_id": "...", "display_name": "..."}
        representing reporters who have not yet submitted. Used for @mention text.
    channel_id : channel context passed to task/fetch button.
    report_week : ISO week string shown in the title.
    """
    week_label = f" ({report_week})" if report_week else ""

    # Build @mention entities and corresponding text
    mention_texts = []
    entities = []
    for reporter in pending_reporter_mentions:
        aad_id = reporter.get("aad_id", "")
        display_name = reporter.get("display_name", "팀원")
        mention_id = f"mention-{aad_id}"
        mention_texts.append(f"<at>{display_name}</at>")
        entities.append({
            "type": "mention",
            "text": f"<at>{display_name}</at>",
            "mentioned": {
                "id": aad_id,
                "name": display_name,
            },
        })

    if mention_texts:
        mention_str = ", ".join(mention_texts)
        reminder_body = f"{mention_str} — 오늘 13:00까지 주간 보고를 제출해 주세요."
    else:
        reminder_body = "모든 팀원이 이미 제출했습니다."

    body = [
        {
            "type": "TextBlock",
            "text": f"주간 보고 제출 알림{week_label}",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": reminder_body,
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "마감: 오늘 (목) 13:00",
            "weight": "Bolder",
            "color": "Warning",
            "spacing": "Medium",
        },
    ]

    actions = []
    if pending_reporter_mentions:
        actions.append({
            "type": "Action.Submit",
            "title": "보고서 작성하기",
            "data": {
                "type": "task/fetch",
                "data": {
                    "taskModuleId": "reportForm",
                    "channelId": channel_id,
                    "isLate": False,
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
