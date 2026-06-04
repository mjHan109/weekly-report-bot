# Phase 0 Discovery Summary

## 1. Purpose
To establish the MVP scope for automating weekly report creation, aggregation, and email distribution via Microsoft Teams Bot by channel, and to lay the technical foundation for Phase 1 design and development.

## 2. Confirmed Business Rules

### 2.1 Reporting Deadline and Alert Schedule
- **Deadline:** Every Thursday at 13:00 KST
- **Thursday 10:00:** Channel alert to non-submitters
- **Thursday 13:00:** Aggregation and alert (see below)

### 2.2 Thursday 13:00 Branch Point
- **Auto-aggregate condition:** All designated reporting targets submitted before 13:00
  - → Auto-aggregate executed + team-lead status card sent
- **Manual-aggregate condition:** Any non-submitter or late submitter present
  - → Channel notice (manual aggregation request) + team-lead pending card sent

### 2.3 Late Submission Rules
- **Self-submit only:** Only the non-submitter themselves may submit after 13:00
  - **Team-lead proxy submission strictly prohibited** (ANY circumstance)
- **Aggregation constraint:** If any late submitter exists, manual aggregation only

### 2.4 Email Send Conditions
- **Block condition:** If ANY non-submitter exists, email send is blocked
- **Send condition:** All reports submitted + aggregation complete + team-lead approval
- Alerts: Thursday 10:00 and 13:00 channel notices (email blocked if non-submitters)

### 2.5 Team-Lead Registration and Reporting Target Designation
- **Team-lead registration:** Users in INITIAL_ADMIN_USER_IDS environment variable OR team-lead self-registers
- **Reporting target designation:** Team-lead specifies designated personnel per channel

### 2.6 Reporting Period
- Previous Thursday 13:00:01 ~ Current Thursday 13:00:00 KST

## 3. User Flows

### Flow 1: Team Member On-Time Submission
1. Team member creates weekly report before Thursday 13:00
2. Submits via Bot Task Module
3. Stored in DB (submitted_after_deadline = false)
4. Team member confirmation message

### Flow 2: Team Member Late Self-Submission
1. Team member creates report after Thursday 13:00
2. Submits via Bot Task Module (self only)
3. Stored in DB (submitted_after_deadline = true)
4. Team member confirmation message

### Flow 3: Team-Lead Auto-Aggregate & Email Send
1. Thursday 13:00: Cloud Scheduler trigger
2. Verify all reporting targets submitted
3. Condition met → auto-aggregate, save TeamReport(aggregation_mode=auto)
4. Send team-lead Adaptive Card (channel/DM)
5. Team-lead clicks "Send Email" button
6. Create mail + send via Graph API

### Flow 4: Team-Lead Manual Aggregate & Email Send
1. Thursday 13:00: Non-submitter or late submitter present
2. Channel notice (manual aggregation instruction)
3. Send team-lead Adaptive Card (status: pending aggregation)
4. Team-lead manually aggregates as needed → save TeamReport(aggregation_mode=manual)
5. Team-lead clicks "Send Email" button
6. Create mail + send via Graph API

### Flow 5: Team-Lead Registration
1. User in INITIAL_ADMIN_USER_IDS or team-lead executes /register command
2. Verify Teams User ID, Name, Email
3. Save to DB ChannelConfig (team_lead_id, team_lead_email)
4. Confirmation message

### Flow 6: Reporting Target Designation
1. Team-lead executes Task Module or Adaptive Card choiceSet
2. Display channel member list (multi-select)
3. Save selected members → ChannelReportTarget
4. Confirmation message

## 4. MVP Scope (FR-013~FR-021)

| FR | Title | Description |
|---|---|---|
| FR-013 | Thursday 10:00 Channel Alert | Channel notice to non-submitters |
| FR-014 | Team-Lead Registration | INITIAL_ADMIN or team-lead self-registers |
| FR-015 | Thursday 13:00 Alert + Status Card | Deliver auto/manual aggregation status to team-lead |
| FR-016 | Late Self-Submission | Non-submitter self-submit only after 13:00 (no proxy) |
| FR-017 | Email Block on Non-Submission | Any non-submitter → email send blocked |
| FR-018 | Reporting Target Designation | Team-lead designates reporting targets per channel |
| FR-019 | Auto-Aggregation | All targets submitted before 13:00 → auto-aggregate |
| FR-020 | Manual Aggregation (Team-Lead Only) | Non-submitter/late submitter present → team-lead manual aggregate |
| FR-021 | Team-Lead Status Adaptive Card | 2 states: auto-aggregated complete, manual pending |

## 5. Tech Stack

### 5.1 Backend
- **Framework:** Python FastAPI **OR** Node.js NestJS
  - **Critical:** Must be selected and locked in Phase 1
  - Record decision in `05_project_decisions.md`

### 5.2 Database
- **Production:** PostgreSQL (Google Cloud SQL)
- **Development:** SQLite

### 5.3 Authentication & Graph API
- **Bot authentication:** Bot Framework (Teams)
- **Email send authentication:** Delegated OAuth + PKCE (Microsoft Graph)
- **Graph scopes:** openid, profile, email, offline_access, User.Read, Mail.ReadWrite, Mail.Send
- **Note:** Tenant admin consent required

### 5.4 Infrastructure & Deployment
- **Server:** Google Cloud Run (serverless)
- **Database:** Cloud SQL
- **Secrets:** Secret Manager
- **Scheduling:** Cloud Scheduler (Thursday 13:00, 10:00 triggers)

### 5.5 LLM
- **Model:** Anthropic Claude Sonnet (report generation, aggregation support)

## 6. DB Entities

| Entity | Description | Key Fields |
|---|---|---|
| ChannelConfig | Channel team-lead and mail settings | channel_id, team_lead_id, team_lead_email, created_at |
| ChannelReportTarget | Designated reporting targets per channel | channel_id, user_id, user_email, added_at |
| PersonalReport | Individual team member report | channel_id, user_id, report_content, submitted_at, submitted_after_deadline |
| TeamReport | Aggregated team report | channel_id, aggregation_mode (auto/manual), aggregated_at, aggregated_by |
| RevisionHistory | Report revision history | report_id, content_diff, revised_at, revised_by |
| MailDraft | Email draft | team_report_id, mail_body, created_at, sent_at |
| AuditLog | Audit logging | action, actor, resource, timestamp, details |
| ReminderLog | Reminder history | channel_id, reminder_type (10:00/13:00), sent_at |

**Total: 8 entities** — Detailed schema to be defined in Phase 2

## 7. Key Components

### 7.1 Teams Adapter (`src/adapters/teams/`)
- **Bot Handler:** Teams Bot Framework routing, message ingestion
- **Task Module:** Report submission UI (on-time/late branching)
- **Adaptive Cards:** Team-lead status cards (2 states), channel alert cards
- **Notification Service:** Thursday 10:00, 13:00 channel notices

### 7.2 Reports Service (`src/services/reports/`)
- **Report Lifecycle Manager:** Submission, late submission, status tracking
- **Aggregation State Machine:** Auto-aggregate vs manual-aggregate logic
- **Deadline Handler:** Thursday 13:00 branch point logic
- **Submission Validator:** Validate designated target, deadline compliance

### 7.3 Mail Service (`src/services/mail/`)
- **Graph OAuth Handler:** Delegated OAuth + PKCE flow
- **Mail Composer:** Generate email body (report-based)
- **Mail Sender:** Invoke Graph Mail.Send API
- **Mail Draft Manager:** Manage MailDraft entity

### 7.4 LLM Service (`src/services/llm/`)
- **Prompt Manager:** Manage prompt templates
- **LLM Client:** Anthropic Claude API wrapper
- **Report Generation Helper:** Assist report authoring

### 7.5 API Layer (`src/api/`)
- **REST Endpoints:** /submit, /aggregate, /send-mail, /register, /set-targets
- **OAuth Callback:** `/auth/callback` (receive Graph token)
- **ACL Middleware:** Validate team-lead authority (aggregate, send-mail)

### 7.6 Infrastructure (`infra/`)
- **Cloud Scheduler Config:** Thursday 10:00, 13:00 HTTP POST triggers
- **Cloud Run Deployment:** Dockerfile, environment variables
- **Secret Manager Integration:** Secret injection

### 7.7 Teams App Package (`teams-app/manifest/`)
- **manifest.json:** Bot ID, scopes, commands, messaging extensions
- **Task Module Config:** Deeplink-based Task Module invocation

## 8. Open Questions

### 8.1 Technical Decisions (to resolve in Phase 1)
1. **Backend framework:** FastAPI vs NestJS → **Must decide in Phase 1**
2. **Team-lead Adaptive Card delivery:** Channel notice vs 1:1 DM → Phase 1 ADR needed
3. **Late submission deadline:** How many hours after 13:00 accepted? → Business policy decision
4. **Adaptive Card update:** Update-in-place (store activity ID) vs re-post → Phase 1 ADR
5. **Reporting target designation UX:** Task Module vs Adaptive Card choiceSet → Phase 1 choice
6. **Late submission completion detection:** Cloud Scheduler sufficient? → Consider report service event hook

### 8.2 Implementation Specifications
- Graph OAuth callback endpoint detailed design
- Cloud Scheduler trigger payload format
- Reporting week boundary handling (exactly at 13:00:00)

## 9. Risks

| Risk ID | Title | Description | Impact | Mitigation |
|---|---|---|---|---|
| RISK-01 | Backend framework undecided | FastAPI vs NestJS not chosen | High | Decide via Phase 1 ADR early |
| RISK-02 | OAuth token lifecycle | Team-lead change scenario, token refresh logic undefined | Medium | Define token refresh strategy in Phase 1 design |
| RISK-03 | Late submission completion detection | Cloud Scheduler polling alone insufficient | Medium | Consider event hook in report service |
| RISK-04 | Team-lead card delivery channel | Channel vs 1:1 DM affects implementation | Low | Clarify business requirements in Phase 1 |
| RISK-05 | Graph mail scope permissions | Mail.ReadWrite, Mail.Send require admin consent | Medium | Coordinate with tenant admin beforehand |
| RISK-06 | Adaptive Card update strategy | Update-in-place vs re-post affects UX | Low | Review UX in Phase 1, then decide |
| RISK-07 | Reporting period boundary case | Exact 13:00:00 submission timing issue | Low | Ensure database timestamp precision (millisecond) |
| RISK-08 | INITIAL_ADMIN_USER_IDS bootstrap | Initial admin setup process undefined | Medium | Write deployment operations guide in Phase 1 |

## 10. Phase 1 Handoff

### 10.1 Decisions Required
- [ ] Backend framework selection (FastAPI OR NestJS) → record in `05_project_decisions.md`
- [ ] Team-lead card delivery channel (channel vs DM)
- [ ] Late submission deadline (13:00 + N hours)
- [ ] Adaptive Card update strategy (update-in-place vs re-post)
- [ ] Reporting target designation UX (Task Module vs choiceSet)

### 10.2 Architecture Decision Records (ADRs) to Write
1. **ADR-001:** Task Module vs Native Form
2. **ADR-002:** Delegated OAuth vs Application OAuth
3. **ADR-003:** Channel ID as Partition Key
4. **ADR-004:** No Team-Lead Proxy Submit Policy
5. **ADR-005:** Cloud Scheduler vs In-Process Cron
6. **ADR-006:** Adaptive Card Update Strategy

### 10.3 Documents & Deliverables to Produce
- [ ] Component Architecture Diagram (with mockups)
- [ ] Graph OAuth Callback Flow (sequence diagram)
- [ ] Cloud Scheduler Endpoint Detailed Design
- [ ] Final DB Entity List (prepare for Phase 2 schema)
- [ ] **phase-1-architecture.md** (ko + en synchronized)

### 10.4 Items to Carry Forward to Phase 2
- Detailed DB schema definition (entity fields, constraints, indexes)
- Graph OAuth token refresh and expiration handling logic
- Cloud Scheduler cloud function implementation (Python/Node selection)
- Adaptive Card JSON templates
- Test Plan & Test Cases
- Deployment & Operations Manual

---

**Document Status:** Phase 0 Discovery Confirmed
**Last Updated:** 2026-06-04
**Next Phase:** Phase 1 Architecture & Design ADRs
