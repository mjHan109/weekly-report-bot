# Phase 2 Output — Teams Integration Engineer

Date: 2026-06-04
Role: @teams-integration-engineer

---

## 1. Overview

The Teams integration layer has been fully implemented for Phase 2 MVP. It is
built on Bot Framework CloudAdapter (botbuilder-core + botbuilder-integration-aiohttp)
and covers four Korean bot commands, Task Module report input, six Adaptive Card
types, and proactive channel-notification scheduler jobs.

---

## 2. Files Created

### Bot Adapter Layer

| File | Purpose |
|---|---|
| `src/adapters/teams/__init__.py` | Package exports |
| `src/adapters/teams/bot_handler.py` | BotFrameworkAdapter wiring, on_message_activity, task/fetch, task/submit, adaptiveCard/action dispatch |
| `src/adapters/teams/command_router.py` | Korean command string → handler routing |

### Command Handlers

| File | Command | ACL |
|---|---|---|
| `src/adapters/teams/handlers/__init__.py` | — | — |
| `src/adapters/teams/handlers/write_report.py` | 이번 주 보고 작성 | Designated reporter only |
| `src/adapters/teams/handlers/aggregate_report.py` | 팀 주간 보고 취합 | Team lead only |
| `src/adapters/teams/handlers/assign_reporters.py` | 보고 대상 지정 | Team lead only |
| `src/adapters/teams/handlers/register_team_lead.py` | 팀장 등록 | INITIAL_ADMIN or self-registration (ADR-008) |

### Task Module

| File | Purpose |
|---|---|
| `src/adapters/teams/task_module/__init__.py` | Package exports |
| `src/adapters/teams/task_module/report_form.py` | Report input form — fetch payload builder + submit handler |
| `src/adapters/teams/task_module/reporter_select_form.py` | Reporter selection form — fetch payload builder + submit handler |

### Adaptive Cards

| File | Purpose |
|---|---|
| `src/adapters/teams/cards/__init__.py` | Package exports |
| `src/adapters/teams/cards/personal_preview.py` | Per-reporter submission preview posted to channel (not DM) |
| `src/adapters/teams/cards/team_lead_pending.py` | Team-lead status card — N reporters pending, mail blocked |
| `src/adapters/teams/cards/team_lead_all_submitted.py` | Team-lead status card — all submitted, aggregation available |
| `src/adapters/teams/cards/aggregate_preview.py` | LLM aggregation preview + mail approve button |
| `src/adapters/teams/cards/reminder_1000.py` | Thursday 10:00 channel reminder |
| `src/adapters/teams/cards/deadline_1300.py` | Thursday 13:00 deadline channel alert |
| `src/adapters/teams/cards/card_sender.py` | send_card(), update_card(), proactive_send() |

### Notification Scheduler Jobs

| File | Purpose |
|---|---|
| `src/adapters/teams/notification_jobs.py` | post_reminder_card(channel_id), post_deadline_card(channel_id) |

### API Route

| File | Purpose |
|---|---|
| `src/api/routes/bot.py` | POST /api/messages — Bot Framework JWT verification + dispatch |

### Teams App Manifest

| File | Purpose |
|---|---|
| `teams-app/manifest/manifest.json` | Manifest v1.17, four Korean commands, validDomains placeholder |
| `teams-app/manifest/color.png.txt` | Placeholder instructions for 192x192 PNG icon |
| `teams-app/manifest/outline.png.txt` | Placeholder instructions for 32x32 PNG icon |

---

## 3. Key Design Decisions Implemented

### Identity Enforcement (ADR-SEC-006)
Every handler reads the caller's identity exclusively from
`activity.from_.aad_object_id`. The `submitter_aad_id` field inside Task
Module hidden data and submitted form payloads is used for display purposes
only and is never trusted for security decisions.

### Task Module Hidden Fields
Four fields are bound server-side at `task/fetch` time — the client cannot
tamper with them:

```
channel_id       — channel context
submitter_aad_id — submitter AAD ID (display only; not used for security)
report_week      — ISO week string, e.g. "2026-W23"
is_late          — bool — True if the Thursday 13:00 deadline has passed
```

### Card Update-In-Place
The team-lead status card is updated in-place using the `activity_id` stored
in `ChannelConfig`. On a 404 response (message deleted or expired) the code
falls back to `send_card()` and persists the new `activity_id`.

### Channel-Only Notifications (No Personal DM)
Both `post_reminder_card()` and `post_deadline_card()` deliver messages to the
team channel via `CardSender.proactive_send()`. Personal DMs are never used.
@mentions are embedded in the card using the `msteams.entities` array.

### No Proxy Submission (ADR-006)
There is no code path that allows a team lead to submit on behalf of a missing
reporter. After the deadline, non-submitters submit late themselves with
`is_late=True`.

### Team-Lead Registration Dual Gate (ADR-008, ADR-SEC-002)
1. Any user listed in `INITIAL_ADMIN_AAD_IDS` env var may always register.
2. Self-registration is allowed when no team lead exists for a channel.
3. An existing team lead may only be replaced by themselves or an INITIAL_ADMIN.

### Scheduled Alert Times
| Time (KST) | Function | Content |
|---|---|---|
| Thu 10:00 | `post_reminder_card()` | @mention pending reporters + submit button |
| Thu 13:00 | `post_deadline_card()` | Deadline reached; auto-aggregate triggered if all submitted |

---

## 4. Service Layer Dependencies

The following services are under parallel implementation in Phase 2. They are
currently guarded by `try/except ImportError` stubs so the Teams layer can be
developed and tested independently.

| Service | Planned Path | Purpose |
|---|---|---|
| ReportService | `src/services/reports/report_service.py` | Report persistence, pending-reporter queries, ACL |
| ChannelConfigService | `src/services/reports/channel_config_service.py` | Team lead, designated reporters, activity_id, ConversationRef storage |
| DeadlineService | `src/services/reports/deadline_service.py` | Thursday 13:00 deadline elapsed check |
| TeamMemberService | `src/services/reports/team_member_service.py` | Graph API channel member fetch |
| AggregationService | `src/services/llm/aggregation_service.py` | LLM report aggregation |
| MailService | `src/services/mail/mail_service.py` | Graph API mail send |

---

## 5. Teams App Packaging Steps

1. Replace placeholders in `teams-app/manifest/manifest.json`:
   - `${TEAMS_APP_ID}` → unique GUID
   - `${MICROSOFT_APP_ID}` → Bot AAD app registration ID
   - `${BOT_DOMAIN}` → bot hosting domain (e.g. `weeklybot.example.com`)
2. Place real `color.png` (192x192) and `outline.png` (32x32) in the same folder.
3. Zip all three files into a single `.zip` archive.
4. Upload via Teams Admin Center or the Developer Portal (sideload).

---

## 6. Next Steps (Phase 3)

- Implement service layer (`ReportService`, `ChannelConfigService`, etc.)
- Wire DB schema
- Scheduler (`infra/scheduler`) — APScheduler or Azure Functions Timer to fire
  at Thu 10:00 and 13:00 KST
- Unit tests: handler ACL, Task Module form builders, card builders, notification_jobs
- Integration tests: Bot Framework Emulator or ngrok local tunnel
