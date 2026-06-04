# Required Environment and Technical Setup

> **Documentation sync rule:** When changing this document, update `docs/ko/02_required_environment.md` with the same structure and meaning.

## 1. Microsoft 365 Environment
- Microsoft Teams-enabled tenant
- Outlook / Exchange Online account
- Permission to register an app in Microsoft Entra ID
- Access to Teams Developer Portal
- Microsoft 365 Agents Toolkit or Teams app development environment

## 2. Recommended Development Approach
Use Claude Agent Teams to let specialized agents design, implement, review, and test the solution in parallel.

Recommended stack: **Teams Bot + Backend API + Delegated Microsoft Graph API**.

```text
Microsoft Teams (per-channel isolation)
→ Teams Bot / Adaptive Card
→ Backend API
→ Report Service / LLM Service
→ Delegated Microsoft Graph API (team lead OAuth)
→ Outlook Draft / Send
```

## 3. Recommended Backend Stack
- Python FastAPI or Node.js Express/NestJS
- PostgreSQL or SQLite
- ORM such as SQLAlchemy or Prisma
- LLM integration module
- Microsoft Graph API client (Delegated tokens)
- Environment-variable based configuration

## 4. Recommended GCP Setup
- Cloud Run: backend API deployment
- Cloud SQL: report and history storage
- Secret Manager: Graph client secret, refresh tokens, LLM API key
- Cloud Logging: operational logs
- Artifact Registry: container images
- Cloud Scheduler:
  - **Every Thursday 10:00 KST** — non-submitter reminder (channel message)
  - **Every Thursday 13:00 KST** — deadline alert, team lead send-block notice (channel message)

## 5. Local Development Environment
- VS Code
- Microsoft 365 Agents Toolkit extension
- Node.js LTS
- Python 3.11+
- Docker Desktop
- ngrok or dev tunnel
- Git
- Claude Code / Claude Agent Teams

## 6. Microsoft Graph Authentication (Delegated Confirmed)
### 6.1 Bot vs Graph Role Separation
| Component | Role | Auth |
|---|---|---|
| Teams Bot | Commands, Adaptive Cards, approval UI | Bot Framework App ID + Password |
| Backend API | Business logic, DB, LLM | Service auth |
| Graph Mail | Outlook draft and send | **Team lead Delegated OAuth** |

The bot does not access Outlook directly. Mail APIs are called only with tokens delegated by the **team lead's sign-in**.

### 6.2 MVP Delegated OAuth Flow
1. Register app in Entra ID (Web/API linked with Bot registration)
2. On first mail feature use, team lead OAuth sign-in (Authorization Code + PKCE)
3. Store refresh token encrypted in Secret Manager/DB
4. Draft: `POST /me/messages`
5. After team lead `발송` approval: `POST /me/sendMail` or draft send

Do **not** use application-only permissions to access user mailboxes in MVP.

### 6.3 MVP Graph Scopes (Delegated)
| Scope | Purpose |
|---|---|
| `openid`, `profile`, `email` | User identity |
| `offline_access` | Refresh token |
| `User.Read` | Profile lookup |
| `Mail.ReadWrite` | Draft creation |
| `Mail.Send` | Send after team lead approval |

Admin consent depends on tenant policy. security-reviewer review is mandatory before production.

## 7. Teams Bot and Channel Setup
- **Notifications:** Bot → **team channel messages** only (no reminder DMs)
- **One Bot app**, **per-channel data isolation**
- manifest.json, color.png, outline.png
- bot id, validDomains
- scopes: `personal`, `team`
- command list (Korean MVP: `이번 주 보고 작성`, `팀 주간 보고 취합`, `팀장 등록`)
- Adaptive Card templates (preview and actions)
- **Task Module** (`task/fetch`) — weekly report input form
- Channel ID is the primary key for reports, settings, aggregation, and send

## 8. DB Schema
- Detailed schema is defined **in parallel with development**.
- Phase 1: confirm core entity list
- Phase 2: refine via migrations
- Candidate entities: `ChannelConfig`, `PersonalReport`, `TeamReport`, `RevisionHistory`, `MailDraft`, `AuditLog`, `ReminderLog`
- `ChannelConfig`: `team_lead_user_id`, `mail_to`, `mail_cc`, `reminder_time` (default 10:00)
- Env `INITIAL_ADMIN_USER_IDS`: comma-separated IDs allowed to run `팀장 등록`

## 9. Example Runtime Configuration
```yaml
app:
  env: local
  base_url: https://example.com
  timezone: Asia/Seoul
  reporting_week_start: THU_13:00  # previous Thu 13:00:01 through current Thu 13:00:00
  reporting_deadline: THU 13:00
  reminder_default_time: THU 10:00
  reminder_deadline_time: THU 13:00

initial_admin:
  user_ids: ${INITIAL_ADMIN_USER_IDS}

teams:
  bot_id: ${TEAMS_BOT_ID}
  bot_password: ${TEAMS_BOT_PASSWORD}

microsoft_graph:
  tenant_id: ${MS_TENANT_ID}
  client_id: ${MS_CLIENT_ID}
  client_secret: ${MS_CLIENT_SECRET}
  redirect_uri: ${MS_REDIRECT_URI}
  auth_type: delegated  # MVP confirmed

llm:
  provider: anthropic
  model: claude-sonnet
  api_key: ${LLM_API_KEY}

database:
  url: ${DATABASE_URL}
```

## 10. Related Documents
- Confirmed decisions: `docs/en/05_project_decisions.md`
- Graph/Bot details: §6 and `05_project_decisions.md` §5
