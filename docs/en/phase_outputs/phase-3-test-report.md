# Phase 3 Test Report — FR-013 ~ FR-021

Date: 2026-06-04
Author: @qa-engineer
Project: Teams Weekly Report Automation

---

## 1. Scope

The following functional requirements are validated in Phase 3.

| FR | Description |
|---|---|
| FR-013 | Thu 10:00 — send channel reminder to non-submitters |
| FR-014 | Team lead registration — seed admin or first-time registrant only |
| FR-015 | Thu 13:00 — non-submitter channel message + team-lead block card |
| FR-016 | Post-deadline self-submit only (no proxy submission) |
| FR-017 | Mail blocked when any member has not submitted |
| FR-018 | Assign report targets — team lead only |
| FR-019 | Auto-aggregate when all members submit on time |
| FR-020 | Manual aggregate — team lead only, after all late members submit |
| FR-021 | Team-lead Adaptive Card in two states (waiting / aggregate-mail guidance) |

> FR-021 (Adaptive Card UI) is excluded from unit testing due to Bot Framework
> card-rendering dependencies and is covered by manual E2E verification.

---

## 2. Test File Structure

```
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures (in-memory SQLite, domain objects)
├── services/
│   ├── __init__.py
│   ├── test_submission_service.py       # FR-016, FR-017
│   ├── test_aggregation_service.py      # FR-019, FR-020
│   ├── test_deadline_service.py         # FR-013, FR-015, FR-019, FR-020
│   ├── test_week_utils.py               # Deadline time calculation
│   ├── test_team_lead_service.py        # FR-014, FR-018
│   └── test_send_service.py             # FR-017, FR-020
├── api/
│   ├── __init__.py
│   └── test_scheduler_routes.py         # FR-013, FR-015
└── integration/
    ├── __init__.py
    └── test_full_flow.py                # FR-019 E2E (AUTO + MANUAL paths)
```

---

## 3. Coverage by FR

### FR-013 — Thu 10:00 Reminder

| Test | File | What is Verified |
|---|---|---|
| `test_reminder_job_targets_only_non_submitters` | `test_deadline_service.py` | `list_pending()` returns only non-submitters |
| `test_reminder_endpoint_requires_hmac` | `test_scheduler_routes.py` | 401 when HMAC headers are absent |
| `test_reminder_endpoint_rejects_invalid_hmac` | `test_scheduler_routes.py` | 401 when signature is wrong |

### FR-014 — Team Lead Registration

| Test | File | What is Verified |
|---|---|---|
| `test_register_allowed_for_initial_admin` | `test_team_lead_service.py` | Seed admin can always register |
| `test_register_allowed_for_self` | `test_team_lead_service.py` | First-time setup is open to anyone |
| `test_register_blocked_for_non_admin_non_self` | `test_team_lead_service.py` | Non-seed admin blocked from replacing existing lead |
| `test_missing_initial_admin_ids_raises_at_startup` | `test_team_lead_service.py` | RuntimeError when INITIAL_ADMIN_USER_IDS is empty |

### FR-015 — Thu 13:00 Non-Submitter Handling

| Test | File | What is Verified |
|---|---|---|
| `test_deadline_run_manual_mode_when_missing` | `test_deadline_service.py` | Non-submitter present → MANUAL_PENDING |
| `test_deadline_endpoint_requires_hmac` | `test_scheduler_routes.py` | 401 when HMAC headers are absent |
| `test_deadline_endpoint_calls_deadline_service` | `test_scheduler_routes.py` | DeadlineService invoked on valid HMAC |

### FR-016 — Post-Deadline Self-Submit Only

| Test | File | What is Verified |
|---|---|---|
| `test_on_time_submit_sets_status_submitted` | `test_submission_service.py` | On-time → SUBMITTED |
| `test_late_submit_sets_submitted_after_deadline_true` | `test_submission_service.py` | Late → LATE_SUBMITTED + flag=True |
| `test_proxy_submit_blocked` | `test_submission_service.py` | actor≠target raises ProxySubmissionError |
| `test_non_reporter_submit_blocked` | `test_submission_service.py` | Unregistered channel raises SubmissionNotAllowedError |

### FR-017 — Mail Blocked When Any Non-Submitter Exists

| Test | File | What is Verified |
|---|---|---|
| `test_mail_blocked_when_any_pending` | `test_submission_service.py` | `can_send_mail()` returns False |
| `test_gate_check_fails_when_pending_submitters` | `test_send_service.py` | SendService gate 2 fails |
| `test_send_blocked_not_called_when_gate_fails` | `test_send_service.py` | Graph API is never called |

### FR-018 — Assign Report Targets (Team Lead Only)

| Test | File | What is Verified |
|---|---|---|
| `test_assign_reporters_team_lead_only` | `test_team_lead_service.py` | Team lead returns True; ordinary member returns False |

### FR-019 — Auto Aggregate

| Test | File | What is Verified |
|---|---|---|
| `test_deadline_run_auto_mode_when_all_submitted` | `test_deadline_service.py` | All submitted → AUTO_AGGREGATING |
| `test_auto_aggregate_when_all_on_time` | `test_aggregation_service.py` | evaluate() → AWAITING_APPROVAL |
| `test_full_auto_aggregate_flow` | `test_full_flow.py` | E2E: all on-time → mail gate open |

### FR-020 — Manual Aggregate

| Test | File | What is Verified |
|---|---|---|
| `test_manual_pending_when_any_late` | `test_aggregation_service.py` | Non-submitter present → MANUAL_PENDING stays |
| `test_manual_pending_when_any_missing` | `test_aggregation_service.py` | All pending → MANUAL_PENDING stays |
| `test_on_late_submit_updates_missing_count` | `test_aggregation_service.py` | Late submit reduces remaining count |
| `test_all_submitted_after_late_sets_all_complete` | `test_aggregation_service.py` | Last late submitter → AWAITING_APPROVAL |
| `test_deadline_run_idempotent` | `test_deadline_service.py` | Non-COLLECTING status: run() is a no-op |
| `test_gate_check_fails_when_not_awaiting_approval` | `test_send_service.py` | Wrong state → gate 1 fails |
| `test_gate_check_fails_when_actor_not_team_lead` | `test_send_service.py` | Non-lead actor → gate 3 fails |
| `test_full_manual_flow` | `test_full_flow.py` | E2E: late submit → mail gate open |

---

## 4. Fixture Design

`tests/conftest.py` provides the following shared fixtures.

- **`async_session`** — `StaticPool`-based in-memory SQLite `AsyncSession`. Independent DB per test.
- **`channel_config`** — One `ChannelConfig` row (`team_lead_aad_id = "team-lead-aad-001"`).
- **`channel_report_target`** — One active `ChannelReportTarget` (member 1).
- **`two_report_targets`** — Two active targets (for FR-017/FR-020 multi-member scenarios).
- **`collecting_team_report`** — `TeamReport` in COLLECTING status.
- **`pending_personal_report`** — `PersonalReport` in PENDING for member 1.
- **`mock_activity`** — Minimal Bot Framework Activity stub (with `aad_object_id`).

---

## 5. Mock Strategy

| External Dependency | Mocking Approach |
|---|---|
| Microsoft Graph API | `MagicMock()` on `GraphClient.send_draft()` |
| LLM (Anthropic) | Out of scope for Phase 3 |
| Bot Framework send | `MagicMock()` — card dispatch not under test |
| `datetime.now()` | `patch("...submission_service.datetime")` |
| `is_after_deadline()` | `patch(...)` — forces boundary scenarios |
| `get_settings()` | `MagicMock()` — injects seed admin IDs |
| `DeadlineService` | `AsyncMock` — injected in scheduler route tests |

---

## 6. How to Run

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-test.txt

# Run all tests
pytest tests/ -v

# Run by FR (keyword filter)
pytest tests/services/test_submission_service.py -v        # FR-016, FR-017
pytest tests/services/test_aggregation_service.py -v       # FR-019, FR-020
pytest tests/services/test_deadline_service.py -v          # FR-013, FR-015
pytest tests/services/test_week_utils.py -v                # Deadline time calculation
pytest tests/services/test_team_lead_service.py -v         # FR-014, FR-018
pytest tests/services/test_send_service.py -v              # FR-017, FR-020
pytest tests/api/test_scheduler_routes.py -v               # FR-013, FR-015
pytest tests/integration/test_full_flow.py -v              # FR-019 E2E

# Coverage report
pytest tests/ --cov=src/services --cov=src/api --cov-report=term-missing
```

---

## 7. Known Limitations

1. **FR-021 (Adaptive Card)** — Cannot be unit-tested due to Bot Framework rendering dependency. Manual E2E verification is recommended.
2. **Scheduler route full HMAC verification** — `_verify_body_hmac` reads `request.body()` directly; body-byte alignment with TestClient may vary by environment. Additional verification in an integration environment is recommended before production deployment.
3. **DB migration compatibility** — Tests use `Base.metadata.create_all`; any schema drift between tests and Alembic migrations requires separate validation.

---

## 8. Done Criteria (E2E)

All of the following must be satisfied for Phase 3 to be considered complete.

- Full pytest run result: 0 failures, 0 errors.
- All targets submitted + team lead sends mail = cycle complete.
- At 13:00, mail is blocked when any non-submitter exists.
- Proxy submission attempt raises `ProxySubmissionError`.
- Non-seed-admin attempt to change team lead raises `TeamLeadRegistrationError`.
