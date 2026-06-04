---
id: ADR-005
title: Input/Output UI: Task Module vs Adaptive Card
status: Accepted
date: 2026-06-04
---

# ADR-005: Input/Output UI: Task Module vs Adaptive Card

## Status
Accepted

## Context

Teams bot provides two UI mechanisms:

1. **Task Module:** click "task" button in channel message → modal form opens
   - Advantage: multi-field input possible
   - Disadvantage: preview and status display difficult

2. **Adaptive Card:** channel message itself is card → buttons, status shown
   - Advantage: preview, status, actions clearly displayed
   - Disadvantage: complex forms difficult

**Question:** which UI where?

## Decision

**Use Task Module for input (data collection), Adaptive Card for output (status/actions).**

| Feature | User | UI Type | Rationale |
|---|---|---|---|
| Write personal report | Team member | Task Module | multi-field input (title, content, attachments) |
| Assign reportees | Team lead | Task Module | user selection (multi-select) |
| Register team lead | Admin/self | Adaptive Card | simple form (channel ID, team name) |
| Personal report preview | Team member | Adaptive Card | submitted status, "request revision" button |
| Team lead status card | Team lead | Adaptive Card | missing reporters list, aggregate button |
| Aggregated report preview | Team lead | Adaptive Card | aggregated status, "approve" button |
| Regular reminder | Team member | Adaptive Card | "still missing" status, submit button |
| Deadline reminder | Team member | Adaptive Card | "auto/manual aggregation starting" notification |

## Rationale

### 1. Task Module Optimized for Data Collection
- HTML form rendering → field validation possible
- Multi-field input natural (report title, content, etc.)
- Modal UI minimizes conversation disruption
- submit → fetch/submit invoke clear flow

### 2. Adaptive Card Optimized for Status Display
- Card itself visualizes status (submitted, awaiting approval, mail sent)
- Button actions (approve, request revision, aggregate) explicit
- List display (N missing reporters) visually clear
- Scheduled reminders (Thu 10:00, 13:00) natural fit

### 3. Combination Improves UX
- Write → Task Module (non-disruptive)
- Check status → Adaptive Card (at a glance)
- Reduced modal fatigue

### 4. Implementation Complexity Balanced
- Task Module: fetch (HTML render), submit (JSON parse)
- Adaptive Card: JSON definition, action invoke handler
- Different patterns reduce code duplication

## Consequences

### Positive
- **UX Clarity:** input and output clearly separated
- **Implementation Simplicity:** each UI type purpose-optimized
- **User Fatigue:** modal exposure minimized

### Drawbacks
- **Dual Handling:** bot_handler handles both task and card
- **Test Complexity:** both flow tests needed

### Constraints
- Task Module can only submit (no real-time status display)
- Adaptive Card unsuitable for many-field input

## Implementation Details

### Task Module (Input)

**Fetch:**
```
POST /api/messages
{
  "type": "invoke",
  "name": "task/fetch",
  "value": {
    "data": {
      "action": "write_report"  // or "assign_targets", "register_lead"
    }
  }
}

Response:
{
  "task": {
    "type": "continue",
    "value": {
      "title": "Write Weekly Report",
      "height": "medium",
      "url": "https://backend/task-module?action=write_report"
    }
  }
}
```

**Submit:**
```
POST /api/messages
{
  "type": "invoke",
  "name": "task/submit",
  "value": {
    "data": {
      "action": "write_report",
      "title": "This Week Highlights",
      "content": "..."
    }
  }
}
```

### Adaptive Card (Output)

```json
{
  "type": "message",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "contentUrl": null,
      "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
          {
            "type": "TextBlock",
            "text": "Personal Report - Submitted",
            "weight": "bolder"
          }
        ],
        "actions": [
          {
            "type": "Action.OpenUrl",
            "title": "Request Revision",
            "url": "..."
          }
        ]
      }
    }
  ]
}
```

## References

- [Teams Task Module](https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/task-modules/task-modules-bots)
- [Adaptive Cards](https://adaptivecards.io/)
- [Bot Framework Card Actions](https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-actions)
