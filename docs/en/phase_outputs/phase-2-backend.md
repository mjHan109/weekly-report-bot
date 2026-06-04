# Phase 2 Backend Implementation Output

Date: 2026-06-04
Author: @backend-developer

---

## 1. Overview

This document covers the implementation of the backend core layer for the
Teams Weekly Report Automation project.
Stack: FastAPI (Python 3.12+), SQLAlchemy 2.x async, Alembic, pydantic-settings.
All confirmed decisions from Phase 1 ADRs are enforced.

---

## 2. Files Created

### Project Setup
| File | Description |
|---|---|
| `src/__init__.py` | Backend package root |
| `src/main.py` | FastAPI app, router mounting, lifespan startup validation |
| `requirements.txt` | Full dependency list (fastapi, sqlalchemy, alembic, anthropic, etc.) |
| `.env.example` | All required environment variables with descriptions |

### Domain Models (`src/domain/`)
| File | Description |
|---|---|
| `src/domain/__init__.py` | Domain layer package |
| `src/domain/enums.py` | `AggregationMode`, `ReportStatus`, `TeamReportStatus` |
| `src/domain/models/base.py` | `DeclarativeBase`, `TimestampMixin` (UTC created_at/updated_at) |
| `src/domain/models/channel_config.py` | `ChannelConfig` — per-channel settings, team_lead_aad_id |
| `src/domain/models/channel_report_target.py` | `ChannelReportTarget` — designated report members |
| `src/domain/models/personal_report.py` | `PersonalReport` — includes `submitted_after_deadline` |
| `src/domain/models/team_report.py` | `TeamReport` — includes `aggregation_mode` enum column |
| `src/domain/models/revision_history.py` | `RevisionHistory` — edit trail for aggregated content |
| `src/domain/models/mail_draft.py` | `MailDraft` — Graph API mail payload |
| `src/domain/models/audit_log.py` | `AuditLog` — immutable event log |
| `src/domain/models/reminder_log.py` | `ReminderLog` — reminder dispatch records |

### Infrastructure (`src/infra/`)
| File | Description |
|---|---|
| `src/infra/__init__.py` | Infrastructure layer package |
| `src/infra/config.py` | `Settings` (pydantic-settings), `get_settings()` cached singleton |
| `src/infra/db.py` | Async engine, `async_sessionmaker`, `get_db` dependency, `create_tables()` |

### Repositories (`src/domain/repositories/`)
| File | Description |
|---|---|
| `src/domain/repositories/__init__.py` | Repository exports |
| `src/domain/repositories/base.py` | `ChannelScopedRepository` — enforces `_require_channel_id` |
| `src/domain/repositories/channel_config_repo.py` | `ChannelConfigRepository` |
| `src/domain/repositories/personal_report_repo.py` | `PersonalReportRepository` |
| `src/domain/repositories/team_report_repo.py` | `TeamReportRepository` |

### Services (`src/services/`)
| File | Description |
|---|---|
| `src/services/__init__.py` | Services layer package |
| `src/services/reports/__init__.py` | Report services package |
| `src/services/reports/week_utils.py` | `get_week_deadline()`, `week_key_from_dt()`, `is_after_deadline()` |
| `src/services/reports/submission_service.py` | `SubmissionService.submit()` — proxy block, late detection |
| `src/services/reports/aggregation_service.py` | `AggregationService` — state machine transitions, `can_send_mail()` |
| `src/services/reports/deadline_service.py` | `DeadlineService.run()` — AUTO/MANUAL decision, idempotent |
| `src/services/acl/__init__.py` | ACL services package |
| `src/services/acl/team_lead_service.py` | `TeamLeadService` — team lead registration, `validate_team_lead()` |

### API Routes (`src/api/`)
| File | Description |
|---|---|
| `src/api/__init__.py` | API layer package |
| `src/api/dependencies.py` | `inject_channel_config`, `verify_scheduler_hmac`, `verify_hmac_signature` |
| `src/api/routes/__init__.py` | Route package |
| `src/api/routes/health.py` | `GET /health` — includes DB connectivity probe |
| `src/api/routes/scheduler.py` | `POST /internal/scheduler/reminder`, `POST /internal/scheduler/deadline` |

### Alembic Migrations
| File | Description |
|---|---|
| `alembic.ini` | Alembic config (DB URL injected from Settings, not hard-coded) |
| `alembic/env.py` | Async-compatible env, auto-detects ORM models |
| `alembic/versions/.gitkeep` | Initialises the versions directory |

---

## 3. Key Business Rules Implemented

### 3.1 Channel ID Isolation
- Every table carries a `channel_id` partition key column.
- `ChannelScopedRepository._require_channel_id()` raises `ValueError` immediately for None/empty values.
- All queries enforce `WHERE channel_id = ?`.

### 3.2 Proxy Submission Prevention
First guard in `submission_service.submit()`:
```python
if actor_aad_id != target_aad_id:
    raise ProxySubmissionError(...)
```
`actor_aad_id` must be extracted from `activity.from.aadObjectId` in the Teams Bot adapter.

### 3.3 Post-Deadline Self-Submit Only
- `is_after_deadline(week_key)` determines timing.
- Late submissions set `status = LATE_SUBMITTED` and `submitted_after_deadline = True`.
- Only permitted when TeamReport is in `MANUAL_PENDING` (or `COLLECTING` for race-condition tolerance).
- Proxy prevention guard always runs first — a team lead cannot submit for someone else even post-deadline.

### 3.4 Mail Send Gate
`AggregationService.can_send_mail()`:
- TeamReport must be in `AWAITING_APPROVAL`.
- Any member still in `PENDING` blocks send: returns `(False, "Cannot send mail: N non-submitter(s)")`.

### 3.5 State Machine Transitions
```
COLLECTING → (Thu 13:00 deadline_service.run())
    ├─ All submitted → AUTO_AGGREGATING → (aggregation_service.evaluate()) → AWAITING_APPROVAL
    └─ Missing members → MANUAL_PENDING → (all late submits in via on_late_submit()) → AWAITING_APPROVAL
                                                                                    ↓
                                                                               MAIL_SENT
```

### 3.6 Scheduler HMAC Authentication
- `X-Scheduler-Sig`: `HMAC-SHA256("{timestamp}:{body}")` hex digest.
- `X-Scheduler-Ts`: Unix timestamp used during signing.
- `verify_hmac_signature()` uses `hmac.compare_digest()` for timing-safe comparison.

### 3.7 Week Deadline Computation
`get_week_deadline(week_key) -> datetime (UTC)`:
- Computes Thursday 13:00 Asia/Seoul for the given ISO week and converts to UTC.
- Example: `"2026-W23"` → `2026-06-04T04:00:00+00:00`

### 3.8 INITIAL_ADMIN_USER_IDS Startup Validation
In `src/main.py` lifespan:
```python
if not settings.initial_admin_user_ids:
    raise RuntimeError("INITIAL_ADMIN_USER_IDS is missing or empty.")
```
The application refuses to start if no seed admin IDs are provided.

---

## 4. Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | SQLAlchemy async URL (asyncpg or aiosqlite) |
| `AZURE_TENANT_ID` | Yes | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Yes | Azure AD app client ID |
| `AZURE_CLIENT_SECRET` | Yes | Azure AD app client secret |
| `BOT_APP_ID` | Yes | Bot Framework App ID |
| `BOT_APP_PASSWORD` | Yes | Bot Framework App Password |
| `SCHEDULER_HMAC_SECRET` | Yes | Shared secret for scheduler HMAC-SHA256 |
| `INITIAL_ADMIN_USER_IDS` | Yes | Comma-separated seed team lead AAD Object IDs |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `ANTHROPIC_MODEL` | Optional | Model to use (default: `claude-sonnet-4-6`) |
| `APP_TIMEZONE` | Optional | Timezone for deadline computation (default: `Asia/Seoul`) |
| `DEBUG` | Optional | Enables `/docs` when `true` (default: `false`) |
| `LOG_LEVEL` | Optional | Log level (default: `INFO`) |

---

## 5. Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with real values

# 3. Run DB migrations (first time)
alembic upgrade head

# 4. Start development server
uvicorn src.main:app --reload --port 8000

# 5. Health check
curl http://localhost:8000/health
```

### SQLite for quick local development (no separate DB)
In `.env`:
```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

---

## 6. Alembic Migration Commands

```bash
# Check current migration state
alembic current

# Apply all pending migrations
alembic upgrade head

# Auto-generate migration after ORM changes
alembic revision --autogenerate -m "add column X to table Y"

# Roll back one step
alembic downgrade -1
```

---

## 7. Integration Points for Other Agents

- `src/adapters/teams/` — Bot handlers calling `SubmissionService.submit()` must pass `actor_aad_id` from `activity.from.aadObjectId` exactly as-is.
- `src/services/mail/send_service.py` — Must call `AggregationService.can_send_mail()` before dispatching any mail.
- External scheduler — Call `POST /internal/scheduler/reminder` at Thu 01:00 UTC and `POST /internal/scheduler/deadline` at Thu 04:00 UTC, with HMAC signature headers attached.
