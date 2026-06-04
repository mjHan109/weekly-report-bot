# Phase 1 Architecture Summary

## Overview

Phase 1 of the Teams Weekly Report Automation project has completed architectural design and confirmed key decisions. This document consolidates the confirmed architecture with 8 technical decisions (ADR-001~008) and 7 security decisions (ADR-SEC-001~007), and identifies handoff points to Phase 2.

---

## 1. Confirmed Decision: FastAPI (Python 3.12+)

### Backend Framework
- **Runtime:** FastAPI (Python 3.12+)
- **ORM:** SQLAlchemy 2.x (async) + Alembic (migrations)
- **LLM SDK:** Anthropic anthropic-sdk (Claude Sonnet)
- **Validation:** Pydantic v2

### Rationale
- Anthropic Python SDK is the most natural interface for LLM integration
- msgraph-sdk-python is Python-first, making Graph API calls explicit
- async/await native support for high concurrency
- Pydantic models solve data validation and serialization simultaneously

### Rejected Alternatives
- Node.js: msgraph-sdk-js is second-generation, weak LLM SDK ecosystem
- Go: No Python LLM SDK, msgraph-sdk-go lacks queue concepts

---

## 2. 5-Layer Component Architecture

### Layer 1: Teams Adapter (`src/adapters/teams/`)

**bot_handler.py**
- BotFrameworkAdapter initialization and Activity routing
- JWT verification (prerequisite, ADR-SEC-007)
- Channel ID extraction and validation

**task_module.py**
- Task Module fetch handler: returns report form HTML or team-lead registration form
- Task Module submit handler: FormData parsing and service layer invocation

**adaptive_cards.py**
- 6 card templates defined (JSON schema, Phase 2 for final definition)
- Card action invoke handlers

**notification_jobs.py**
- Proactive message dispatch to channels
- Scheduled reminders at Thu 10:00, 13:00

### Layer 2: API/Routing (`src/api/routes/`)

**bot.py**
- `POST /api/messages` — Bot Framework entry point
- Activity type routing (message, invoke, ...)

**reports.py**
- `POST /api/reports/submit` — personal report submission
- `POST /api/reports/aggregate` — team report aggregation (team-lead only)
- `POST /api/reports/revise` — revision request
- `GET /api/reports/{report_id}` — report detail retrieval

**scheduler.py**
- `POST /internal/scheduler/reminder` — Thu 10:00 (Cloud Scheduler)
- `POST /internal/scheduler/deadline` — Thu 13:00 (Cloud Scheduler)
- HMAC-SHA256 verification (ADR-004)

**health.py**
- `GET /health` — liveness probe

**auth.py**
- `GET /auth/callback?code=...&state=...` — OAuth callback
- PKCE validation, token storage

### Layer 3: Service Layer (`src/services/`)

**reports/submission_service.py**
- `submit(channel_id, owner_aad_id, week_key, content) → PersonalReport`
- Late submission detection → event emission
- ADR-006: owner_aad_id validation

**reports/aggregation_service.py**
- `aggregate(channel_id, week_key) → TeamReport`
- LLM invocation (delegated to generation_service)
- State transition handling

**reports/deadline_service.py**
- `check_deadline(channel_id, week_key) → (mode: AUTO|MANUAL, missing_reporters: List[str])`
- Thu 13:00 scheduler entry point

**reports/revision_service.py**
- `request_revision(channel_id, report_id, feedback) → void`
- Card update and channel notification

**mail/draft_service.py**
- `draft_team_report(channel_id, team_report_id) → DraftMail`
- Draft creation, Graph API POST /me/messages

**mail/send_service.py**
- `send_team_report(channel_id, team_report_id, actor_aad_id) → Mail`
- Triple-gate verification (ADR-SEC-003)
- Graph API POST /me/messages/{id}/send

**llm/generation_service.py**
- `generate_aggregation(personal_reports: List[str]) → str`
- Anthropic SDK invocation

**acl/team_lead_service.py**
- `register_team_lead(channel_id, user_aad_id) → ChannelConfig`
- Bootstrap validation (ADR-008)
- Transfer validation (existing channels only)

### Layer 4: Domain/DB (`src/domain/`)

**models/** — SQLAlchemy ORM (8 entities)
1. `ChannelConfig` — channel metadata, team-lead OID, week_key
2. `ChannelReportTarget` — reportees per channel (OID list)
3. `ReportSlot` — per-reportee slot (owner_aad_id, week_key)
4. `PersonalReport` — individual report (content, status: DRAFT|SUBMITTED|REVISED)
5. `TeamReport` — team report (aggregated_content, status: COLLECTING|AUTO_AGGREGATING|MANUAL_PENDING|AWAITING_APPROVAL|MAIL_SENT)
6. `Mail` — mail object (graph_message_id, status: DRAFT|SENT|CANCELLED)
7. `Token` — OAuth token metadata (team_lead_aad_id, expires_at) [actual token in Secret Manager]
8. `AuditLog` — security audit log

**repositories/**
- `ChannelScopedRepository` — base class, channel_id mandatory in all queries (ADR-002)
- `PersonalReportRepository`
- `TeamReportRepository`
- `ChannelConfigRepository`
- `MailRepository`

**enums.py**
- `AggregationMode` = AUTO | MANUAL
- `ReportStatus` = DRAFT | SUBMITTED | REVISED
- `TeamReportStatus` = COLLECTING | AUTO_AGGREGATING | MANUAL_PENDING | AWAITING_APPROVAL | MAIL_SENT

### Layer 5: Infrastructure (`infra/`)

**scheduler/** — Cloud Scheduler config (Terraform/JSON)
- Reminder job: Thu 10:00 KST
- Deadline job: Thu 13:00 KST
- POST target, X-Scheduler-Sig HMAC header

**graph_client.py**
- `GraphAuthProvider` — OAuth flow (PKCE + state)
- Token store: GCP Secret Manager
- Retry logic: exponential backoff (500ms, 2x, max 3), circuit breaker (5 failures)

**db.py**
- async SQLAlchemy engine config
- Alembic migration path

---

## 3. Aggregation State Machine

### 6 States
1. **COLLECTING** — submission in progress
2. **AUTO_AGGREGATING** — 13:00 all submitted, LLM aggregating
3. **MANUAL_PENDING** — late submissions exist, team-lead manual aggregate required
4. **AWAITING_APPROVAL** — LLM aggregation done, team-lead approval/mail pending
5. **MAIL_SENT** — mail dispatched, final state
6. (implicit) **DEADLINE_PASSED** — state frozen post-13:00 (no transitions)

### 7 Transitions

| From | To | Trigger | Condition |
|---|---|---|---|
| COLLECTING | AUTO_AGGREGATING | deadline_service.check_deadline() at Thu 13:00 | all submitted |
| COLLECTING | MANUAL_PENDING | submission_service.submit() | submitted_after_deadline=true |
| AUTO_AGGREGATING | AWAITING_APPROVAL | LLM aggregation done | aggregation_service callback |
| MANUAL_PENDING | MANUAL_PENDING | submission_service.submit() | another late submit |
| MANUAL_PENDING | AWAITING_APPROVAL | aggregation_service.aggregate() team-lead call | team-lead manual aggregate |
| AWAITING_APPROVAL | MAIL_SENT | mail_send_service.send() | mail sent successfully |
| any state | AWAITING_APPROVAL | revision_service.request_revision() | post-approval feedback |

### State Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  COLLECTING                                                  │
│   │                                                           │
│   ├─ (13:00, all submitted) ─→ AUTO_AGGREGATING             │
│   │                                 │                         │
│   │ (late submit)                   │                         │
│   ├─────→ MANUAL_PENDING ←─────────┘                         │
│           │   ↑                                               │
│           │   └─ (another late submit)                       │
│           │                                                  │
│           └─ (team-lead: aggregate) ──→ AWAITING_APPROVAL   │
│                                          │                   │
│                                          ├─ (send mail)     │
│                                          │  ──→ MAIL_SENT   │
│                                          │                   │
│                                          └─ (revision) ───┐ │
│                                             ────←─────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Teams Integration

### 4 Bot Commands

| Command | Actor | UI | Endpoint |
|---|---|---|---|
| Write weekly report | Team member | Task Module | POST /api/messages (invoke, action=submit) |
| Aggregate team report | Team lead | Adaptive Card | POST /api/messages (invoke, action=aggregate) |
| Assign reportees | Team lead | Task Module | POST /api/messages (invoke, action=assign_targets) |
| Register team lead | Admin/self | Adaptive Card | POST /api/messages (invoke, action=register_lead) |

### 6 Adaptive Card Templates

1. **personal_report_preview_card**
   - Post-submission personal report preview
   - Content summary, submission time, status badge
   - "Request revision" action available

2. **team_lead_status_card_state1_pending**
   - COLLECTING state with missing reporters list
   - "N missing, mail unavailable"
   - Team lead subscribes to periodic updates

3. **team_lead_status_card_state2_all_submitted**
   - COLLECTING or AUTO_AGGREGATING with all submitted
   - "All submitted, aggregate button enabled"
   - Reverts to state 1 on late submission

4. **aggregate_report_preview_card**
   - Post-aggregation team report preview for team lead
   - "Approve" or "Request revision" actions

5. **scheduled_reminder_card_thu_1000**
   - Thu 10:00 KST scheduled reminder
   - "Report still missing" check
   - Submit button included

6. **scheduled_deadline_card_thu_1300**
   - Thu 13:00 KST deadline notification
   - "Automatic aggregation starting" or "Manual aggregate required" guidance

---

## 5. Graph API / OAuth Design

### OAuth Flow: Authorization Code + PKCE

1. **Team Lead Initialization**
   - `GET /auth/start?channel_id=...` — state (128-bit entropy), PKCE code_challenge generated
   - 3-minute TTL state stored
   - Microsoft OAuth redirect: `https://login.microsoftonline.com/.../oauth2/v2.0/authorize?...`

2. **Callback**
   - `GET /auth/callback?code=...&state=...`
   - state verification, code_verifier PKCE verification
   - POST `/token` — Graph API, Authorization Code + PKCE → access_token + refresh_token

3. **Token Store**
   - GCP Secret Manager (per-channel per-team-lead OID)
   - `graph-access-token-{oid}` — with expiration time
   - `graph-refresh-token-{oid}` — for refresh
   - `graph-token-metadata-{oid}` — metadata (scopes, issued_at)

4. **Token Refresh**
   - Automatic: graph_client.ensure_valid_token(team_lead_aad_id)
   - Atomic write: new refresh token written to Secret Manager first, then used (ADR-SEC-004)
   - Write failure → operation abort, re-auth required

### Mail Endpoints

| Task | Method | Endpoint | Permission |
|---|---|---|---|
| Create draft | POST | /me/messages | Mail.Send |
| Update draft | PATCH | /me/messages/{message-id} | Mail.Send |
| Send mail | POST | /me/messages/{message-id}/send | Mail.Send |
| Delete mail | DELETE | /me/messages/{message-id} | Mail.Send |

### Permission Scopes
- `Mail.Send` (delegated only)
- `User.Read` (profile, display name)

### Retry Policy
- Exponential backoff: 500ms initial, 2x multiplier, max 3 retries
- Circuit breaker: 10-minute lockout after 5 consecutive failures
- 429 (throttling): respect Retry-After header

---

## 6. Security Architecture

### Bot Framework JWT Verification (ADR-SEC-007)
- Mandatory execution before all `/api/` and `/internal/` endpoints
- Production: Microsoft public key signature verification
- Development: password-based verification only
- Non-bypassable middleware

### Channel Isolation (ADR-SEC-005)
- **Partition Key:** channel_id (extracted from Bot Framework Activity only)
- **ORM Enforcement:** ChannelScopedRepository base class
- **Validation:** channel_id mandatory first parameter in all service functions
- **Cross-channel attempts:** audit log + rejection

### No-Proxy Submission (ADR-SEC-006)
- **Invariant:** activity.from.aadObjectId == PersonalReport.owner_aad_id
- **Validation:** submission_service.submit() internal check
- **Violation:** 403 Forbidden + audit log

### Triple-Gate Mail Send (ADR-SEC-003)
- **Gate 1:** TeamReport.status == AWAITING_APPROVAL
- **Gate 2:** all ChannelReportTargets have PersonalReport for the week
- **Gate 3:** actor AAD ID == ChannelConfig.team_lead_aad_id
- **Verification:** server-side re-verification pre-send (replay attack prevention)

### Scheduler Authentication (ADR-004)
- **Method:** HMAC-SHA256 (X-Scheduler-Sig header)
- **Secret:** SCHEDULER_HMAC_SECRET env var (stored in Secret Manager)
- **Path:** /internal/* (restricted at reverse proxy too)

### Delegated-Only OAuth (ADR-SEC-001)
- **Policy:** Graph API calls permanently exclude application permissions
- **Validation:** CI lint rule (code review gate)
- **Result:** bot access scoped to team-lead's consented mailbox only

### Team-Lead Registration Dual-Gate (ADR-SEC-002)
- **Condition:** INITIAL_ADMIN_USER_IDS (env var) or self-registration
- **ID Source:** Bot Framework Activity only (payload excluded)
- **Bootstrap Failure:** missing env var causes startup failure (misconfiguration detection)

### Refresh Token Atomicity (ADR-SEC-004)
- **Operation:** new token written to Secret Manager first, then used
- **Failure:** operation abort, re-auth required
- **Result:** 1:1 token version consistency

---

## 7. DB Entities and Channel Isolation

### 8 SQLAlchemy ORM Models

#### 1. ChannelConfig
```
- id (PK, UUID)
- channel_id (UK, indexed)
- team_name (str)
- team_lead_aad_id (str, nullable — unregistered)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 2. ChannelReportTarget
```
- id (PK, UUID)
- channel_id (FK + partition key)
- target_aad_id (str)
- display_name (str, cache only)
- created_at (UTC timestamp)
```

#### 3. ReportSlot
```
- id (PK, UUID)
- channel_id (FK + partition key)
- owner_aad_id (str)
- week_key (str, e.g., "2026-W23")
- status (enum: PENDING|SUBMITTED|REVISED)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 4. PersonalReport
```
- id (PK, UUID)
- channel_id (FK + partition key)
- report_slot_id (FK)
- owner_aad_id (str, denormalize for indexing)
- week_key (str)
- content (text)
- submitted_at (UTC timestamp)
- submitted_after_deadline (bool)
- status (enum: DRAFT|SUBMITTED|REVISED)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 5. TeamReport
```
- id (PK, UUID)
- channel_id (FK + partition key)
- week_key (str)
- aggregation_mode (enum: AUTO|MANUAL)
- aggregated_content (text, nullable until AWAITING_APPROVAL)
- status (enum: COLLECTING|AUTO_AGGREGATING|MANUAL_PENDING|AWAITING_APPROVAL|MAIL_SENT)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 6. Mail
```
- id (PK, UUID)
- channel_id (FK + partition key)
- team_report_id (FK)
- team_lead_aad_id (str)
- graph_message_id (str, nullable until sent)
- status (enum: DRAFT|SENT|CANCELLED)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 7. Token
```
- id (PK, UUID)
- channel_id (FK + partition key)
- team_lead_aad_id (str)
- graph_access_token_ttl (datetime, expires_at)
- graph_refresh_token_ttl (datetime, metadata only)
- created_at (UTC timestamp)
- updated_at (UTC timestamp)
```

#### 8. AuditLog
```
- id (PK, UUID)
- channel_id (FK + partition key)
- actor_aad_id (str, nullable)
- action (str, e.g., "cross_channel_attempt", "proxy_submit_attempt", "mail_send_gate_fail")
- details (JSON)
- created_at (UTC timestamp)
```

### Channel Isolation Enforcement Mechanism

**ChannelScopedRepository Base Class**
```python
class ChannelScopedRepository:
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        # channel_id always included in WHERE clause
        ...

    async def find_all(self, channel_id: str) -> List[T]:
        # no cross-channel queries possible (method signature enforces)
        ...
```

**Service Layer Validation**
```python
async def submit(self, channel_id: str, owner_aad_id: str, ...):
    # first parameter always channel_id
    # extracted from Activity only (trusted source)
```

**Result:**
- Impossible to accidentally query across channels
- ORM queries auto-filter by channel_id
- Audit log records any attempted cross-channel access

---

## 8. Scheduler Design

### Cloud Scheduler Jobs

#### 1. Reminder Job (Thu 10:00 KST)
```
POST https://<backend>/internal/scheduler/reminder
Headers:
  X-Scheduler-Sig: HMAC-SHA256(payload, SCHEDULER_HMAC_SECRET)
  Content-Type: application/json
Body:
  {
    "timestamp": "2026-06-04T10:00:00Z",
    "channels": ["channel-1", "channel-2", ...]
  }
```

**Response Handling:**
- notification_jobs.send_reminder_cards() invoked
- All team members in all channels sent "report still missing" card
- Existing cards updatable (Teams adaptive card refresh token)

#### 2. Deadline Job (Thu 13:00 KST)
```
POST https://<backend>/internal/scheduler/deadline
Headers:
  X-Scheduler-Sig: HMAC-SHA256(payload, SCHEDULER_HMAC_SECRET)
  Content-Type: application/json
Body:
  {
    "timestamp": "2026-06-04T13:00:00Z",
    "channels": ["channel-1", "channel-2", ...]
  }
```

**Response Handling:**
- deadline_service.check_deadline(channel_id, week_key) called per channel
- All members submitted → TeamReport transitions to AUTO_AGGREGATING
  - aggregation_service.aggregate() async task started
  - On LLM aggregation done, auto-transition to AWAITING_APPROVAL
  - Team lead sent "aggregation done, awaiting approval" card
- Late submissions exist → TeamReport stays MANUAL_PENDING
  - Team lead sent "N late, manual aggregate required" card

### Late Submit Event Hook

**Trigger Location:** `submission_service.submit()` when `submitted_after_deadline=true` detected

**Processing:**
1. Event emission (in-process async event bus)
2. Event callback: TeamReport state recalculation
3. Missing reporters re-aggregated
4. Team lead card state updated (channel proactive message refreshes or sends new card)
5. If remaining_missing == 0, update to "all submitted, manual aggregate available" card

---

## 9. Open Items (Handed to Phase 2)

### 1. DB Schema Detail
- [ ] Index strategy per model (FK, UK, covering)
- [ ] Partition key considerations (cloud-native DB partition by channel_id)
- [ ] Audit log retention policy (30 days? 90 days?)

### 2. Adaptive Card JSON Templates
- [ ] personal_report_preview_card detailed schema
- [ ] team_lead_status_card_state1_pending dynamic content (missing reporters list)
- [ ] team_lead_status_card_state2_all_submitted action binding
- [ ] aggregate_report_preview_card revision feedback UI
- [ ] scheduled_reminder_card_thu_1000 report creation button
- [ ] scheduled_deadline_card_thu_1300 auto/manual mode display

### 3. LLM Prompt Design
- [ ] Persona: team lead, high corporate literacy editor
- [ ] Input format: personal reports list (JSON structure)
- [ ] Output format: markdown sectioned summary
- [ ] Safety: sensitive data filtering (emails, etc.)
- [ ] Token limits: max input+output per model

### 4. Mail To/CC Configuration UX
- [ ] Team report authoring allows recipient specification?
- [ ] Default: self (team lead) + escalation recipient?
- [ ] Task Module extension or Adaptive Card?

### 5. Late Submit Time Boundary
- [ ] Max hours post-13:00 KST for late submission?
- [ ] Policy: unlimited? Friday midnight? Next Monday?
- [ ] Max manual aggregation attempts post-auto?

### 6. Teams App Manifest Final Packaging
- [ ] manifest.json — bot ID, scopes, activity types
- [ ] Icons, introductory text
- [ ] Command list and descriptions

### 7. Local Dev Environment Setup
- [ ] Docker Compose (fastapi, postgres, redis)
- [ ] ngrok or devtunnel configuration
- [ ] Teams app side-load instructions
- [ ] Mock scheduler or manual trigger endpoint

---

## 10. Phase 2 Handoff

### Deliverables
1. **Architecture Document** (this document)
2. **15 ADRs** (technical + security decisions)
3. **Project Decisions** (docs/ko/05_project_decisions.md established)
4. **Requirements Spec** (docs/ko/01_requirements_spec.md confirmed)

### Phase 2 Work Order (Recommended)
1. **Infrastructure Setup** (2-3 days)
   - GCP project setup (Secret Manager, Cloud Scheduler)
   - PostgreSQL provisioning (or Cloud SQL)
   - Local dev environment (Docker + ngrok)

2. **DB Schema + Alembic** (3-4 days)
   - SQLAlchemy model detail implementation
   - Migration authoring and test
   - Channel isolation enforcement test

3. **OAuth and Graph Client** (3-4 days)
   - PKCE flow implementation
   - Secret Manager storage
   - Token refresh and circuit breaker

4. **Service Layer** (5-7 days)
   - submission_service, aggregation_service, deadline_service
   - LLM prompt and generation_service
   - mail_draft_service, mail_send_service (triple-gate)

5. **API Routing + Teams Adapter** (4-5 days)
   - bot_handler, task_module, adaptive_cards
   - 6 card templates (JSON)
   - Bot Framework middleware and JWT verification

6. **Scheduler and Notifications** (2-3 days)
   - Cloud Scheduler integration
   - notification_jobs
   - Late submit event hook

7. **Test + Documentation** (5-7 days)
   - Unit test (service, repo)
   - Integration test (API endpoints, OAuth)
   - E2E test (Teams channel)
   - API docs (Swagger/OpenAPI)

### Dependencies Check
- [ ] Azure AD tenant (Teams, Microsoft Graph)
- [ ] GCP project (Secret Manager, Cloud Scheduler, or CloudRun)
- [ ] Developer Teams test environment
- [ ] MongoDB or PostgreSQL (choice)
- [ ] Anthropic API key

### Risk Factors
- **DateTime Management:** ensure no timezone confusion across systems (Python zoneinfo, UTC storage)
- **State Machine:** post-deadline state transition complexity (need robust test coverage)
- **OAuth Token Refresh:** prevent double-refresh in concurrent scenarios
- **Mail Send Gate:** triple-condition re-verification lock contention, deadlock risk

---

## 11. Glossary

| Term | Definition |
|---|---|
| **week_key** | ISO 8601 week number, e.g., "2026-W23" |
| **channel_id** | Teams channel ID (from Bot Framework Activity) |
| **team_lead_aad_id** | Azure AD Object ID (team lead) |
| **owner_aad_id** | Personal report owner AAD Object ID |
| **aggregation_mode** | AUTO (13:00 all submitted) or MANUAL (late submissions exist) |
| **submitted_after_deadline** | submission occurred post-13:00 KST |
| **partition key** | channel_id required in all DB queries |
| **ChannelScopedRepository** | all repositories base class, channel_id enforced |
| **triple-gate** | 3-condition verification pre-mail-send (status + completeness + authority) |
| **PKCE** | Proof Key for Code Exchange (OAuth CSRF prevention) |
| **Adaptive Card** | Microsoft Teams card UI (JSON-based) |
| **Task Module** | Teams in-modal form (Task fetch/submit) |

---

## 12. Reference Documents

- [01_requirements_spec.md](../01_requirements_spec.md) — requirements confirmed
- [02_required_environment.md](../02_required_environment.md) — environment and permissions
- [03_agent_roles.md](../03_agent_roles.md) — agent role definitions
- [05_project_decisions.md](../05_project_decisions.md) — MVP core decisions
- [adr/](../adr/) — 15 ADRs (technical + security)
