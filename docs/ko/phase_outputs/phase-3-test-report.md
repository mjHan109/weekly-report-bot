# Phase 3 테스트 보고서 — FR-013 ~ FR-021

작성일: 2026-06-04
작성자: @qa-engineer
프로젝트: Teams 주간 보고 자동화

---

## 1. 범위

Phase 3에서 검증하는 기능 요구사항은 다음과 같다.

| FR | 설명 |
|---|---|
| FR-013 | 목 10:00 — 미제출자에게 채널 리마인더 발송 |
| FR-014 | 팀장 등록 — seed admin 또는 최초 등록자만 허용 |
| FR-015 | 목 13:00 — 미제출자 채널 메시지 + 팀장 블록 카드 |
| FR-016 | 마감 후 본인 제출만 허용 (대리 제출 금지) |
| FR-017 | 미제출자가 1명이라도 있으면 메일 발송 차단 |
| FR-018 | 보고 대상 지정 — 팀장만 가능 |
| FR-019 | 전원 on-time 제출 시 자동 취합 |
| FR-020 | 수동 취합 — 팀장만, 마감 후 전원 제출 완료 후 |
| FR-021 | 팀장 Adaptive Card 2가지 상태 (대기 / 취합·메일 안내) |

> FR-021(Adaptive Card UI)은 Bot Framework 카드 렌더링 의존성으로 인해
> 본 Phase에서 단위 테스트 대상에서 제외되며, E2E(수동) 검증으로 대체한다.

---

## 2. 테스트 파일 구조

```
tests/
├── __init__.py
├── conftest.py                          # 공통 픽스처 (in-memory SQLite, 도메인 객체)
├── services/
│   ├── __init__.py
│   ├── test_submission_service.py       # FR-016, FR-017
│   ├── test_aggregation_service.py      # FR-019, FR-020
│   ├── test_deadline_service.py         # FR-013, FR-015, FR-019, FR-020
│   ├── test_week_utils.py               # 마감 시간 계산 기반 검증
│   ├── test_team_lead_service.py        # FR-014, FR-018
│   └── test_send_service.py             # FR-017, FR-020
├── api/
│   ├── __init__.py
│   └── test_scheduler_routes.py         # FR-013, FR-015
└── integration/
    ├── __init__.py
    └── test_full_flow.py                # FR-019 E2E (AUTO + MANUAL)
```

---

## 3. FR별 커버리지

### FR-013 — 목 10:00 리마인더

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_reminder_job_targets_only_non_submitters` | `test_deadline_service.py` | `list_pending()` 이 미제출자만 반환하는지 확인 |
| `test_reminder_endpoint_requires_hmac` | `test_scheduler_routes.py` | HMAC 헤더 없으면 401 반환 |
| `test_reminder_endpoint_rejects_invalid_hmac` | `test_scheduler_routes.py` | 잘못된 서명이면 401 반환 |

### FR-014 — 팀장 등록

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_register_allowed_for_initial_admin` | `test_team_lead_service.py` | seed admin은 항상 등록 가능 |
| `test_register_allowed_for_self` | `test_team_lead_service.py` | 최초 등록은 누구나 가능 |
| `test_register_blocked_for_non_admin_non_self` | `test_team_lead_service.py` | 기존 팀장 변경 시 비seed admin 차단 |
| `test_missing_initial_admin_ids_raises_at_startup` | `test_team_lead_service.py` | INITIAL_ADMIN_USER_IDS 미설정 시 RuntimeError |

### FR-015 — 목 13:00 미제출자 처리

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_deadline_run_manual_mode_when_missing` | `test_deadline_service.py` | 미제출자 존재 시 MANUAL_PENDING 전환 |
| `test_deadline_endpoint_requires_hmac` | `test_scheduler_routes.py` | HMAC 헤더 없으면 401 |
| `test_deadline_endpoint_calls_deadline_service` | `test_scheduler_routes.py` | 유효한 HMAC으로 DeadlineService 호출 확인 |

### FR-016 — 마감 후 본인 제출만 허용

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_on_time_submit_sets_status_submitted` | `test_submission_service.py` | on-time 제출 → SUBMITTED |
| `test_late_submit_sets_submitted_after_deadline_true` | `test_submission_service.py` | late 제출 → LATE_SUBMITTED + flag=True |
| `test_proxy_submit_blocked` | `test_submission_service.py` | actor≠target 시 ProxySubmissionError |
| `test_non_reporter_submit_blocked` | `test_submission_service.py` | 미등록 채널 → SubmissionNotAllowedError |

### FR-017 — 미제출자 존재 시 메일 차단

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_mail_blocked_when_any_pending` | `test_submission_service.py` | `can_send_mail()` False 반환 |
| `test_gate_check_fails_when_pending_submitters` | `test_send_service.py` | SendService gate 2 실패 |
| `test_send_blocked_not_called_when_gate_fails` | `test_send_service.py` | Graph API 호출 없음 확인 |

### FR-018 — 보고 대상 지정 (팀장 전용)

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_assign_reporters_team_lead_only` | `test_team_lead_service.py` | 팀장 True / 일반 멤버 False 반환 |

### FR-019 — 자동 취합

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_deadline_run_auto_mode_when_all_submitted` | `test_deadline_service.py` | 전원 제출 → AUTO_AGGREGATING |
| `test_auto_aggregate_when_all_on_time` | `test_aggregation_service.py` | evaluate() → AWAITING_APPROVAL |
| `test_full_auto_aggregate_flow` | `test_full_flow.py` | E2E: 전원 on-time → 메일 게이트 열림 |

### FR-020 — 수동 취합

| 테스트 | 파일 | 검증 내용 |
|---|---|---|
| `test_manual_pending_when_any_late` | `test_aggregation_service.py` | 미제출자 있으면 MANUAL_PENDING 유지 |
| `test_manual_pending_when_any_missing` | `test_aggregation_service.py` | 전원 미제출 시 MANUAL_PENDING 유지 |
| `test_on_late_submit_updates_missing_count` | `test_aggregation_service.py` | late 제출 후 remaining count 확인 |
| `test_all_submitted_after_late_sets_all_complete` | `test_aggregation_service.py` | 마지막 미제출자 제출 → AWAITING_APPROVAL |
| `test_deadline_run_idempotent` | `test_deadline_service.py` | COLLECTING이 아니면 중복 실행 무시 |
| `test_gate_check_fails_when_not_awaiting_approval` | `test_send_service.py` | 잘못된 상태에서 gate 1 실패 |
| `test_gate_check_fails_when_actor_not_team_lead` | `test_send_service.py` | 비팀장 gate 3 실패 |
| `test_full_manual_flow` | `test_full_flow.py` | E2E: late 제출 후 메일 게이트 열림 |

---

## 4. 픽스처 설계

`tests/conftest.py`는 다음 공유 픽스처를 제공한다.

- **`async_session`** — `StaticPool` 기반 인메모리 SQLite `AsyncSession`. 테스트마다 독립적인 DB.
- **`channel_config`** — `ChannelConfig` 1건 (team_lead_aad_id = `team-lead-aad-001`).
- **`channel_report_target`** — `ChannelReportTarget` 1건 (member 1).
- **`two_report_targets`** — 멤버 2명 (FR-017/FR-020 다수 멤버 시나리오용).
- **`collecting_team_report`** — 상태 COLLECTING인 `TeamReport`.
- **`pending_personal_report`** — 상태 PENDING인 `PersonalReport` (member 1).
- **`mock_activity`** — Bot Framework Activity 스텁 (aad_object_id 포함).

---

## 5. 목(Mock) 전략

| 외부 의존성 | 목 방법 |
|---|---|
| Microsoft Graph API | `MagicMock()` — `GraphClient.send_draft()` |
| LLM (Anthropic) | 테스트 범위 외 (Phase 3 미포함) |
| Bot Framework send | `MagicMock()` — 카드 발송 검증 불필요 |
| `datetime.now()` | `patch("...submission_service.datetime")` |
| `is_after_deadline()` | `patch(...)` — 경계값 시나리오 강제 |
| `get_settings()` | `MagicMock()` — seed admin ID 주입 |
| `DeadlineService` | `AsyncMock` — 스케줄러 라우터 테스트에서 주입 |

---

## 6. 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt -r requirements-test.txt

# 전체 실행
pytest tests/ -v

# FR별 실행 (키워드 필터)
pytest tests/services/test_submission_service.py -v        # FR-016, FR-017
pytest tests/services/test_aggregation_service.py -v       # FR-019, FR-020
pytest tests/services/test_deadline_service.py -v          # FR-013, FR-015
pytest tests/services/test_week_utils.py -v                # 마감 시간 계산
pytest tests/services/test_team_lead_service.py -v         # FR-014, FR-018
pytest tests/services/test_send_service.py -v              # FR-017, FR-020
pytest tests/api/test_scheduler_routes.py -v               # FR-013, FR-015
pytest tests/integration/test_full_flow.py -v              # FR-019 E2E

# 커버리지 리포트
pytest tests/ --cov=src/services --cov=src/api --cov-report=term-missing
```

---

## 7. 알려진 제한사항

1. **FR-021 (Adaptive Card)** — Bot Framework 렌더링 환경 의존성으로 단위 테스트 불가. 수동 E2E 검증 권장.
2. **scheduler 라우트 HMAC 전체 검증** — `_verify_body_hmac`가 `request.body()`를 직접 읽는 구조로, TestClient에서의 body 바이트 일치 여부가 환경에 따라 달라질 수 있다. 프로덕션 배포 전 통합 환경에서 추가 검증 필요.
3. **DB 마이그레이션 호환** — 테스트는 `Base.metadata.create_all`로 생성하므로 Alembic 마이그레이션과 스키마 불일치가 발생할 경우 별도 검증 필요.

---

## 8. 완료 기준 (E2E)

다음 조건을 모두 만족해야 Phase 3 완료로 간주한다.

- 전체 pytest 실행 결과: 0 실패, 0 오류
- 제출 대상 전원이 제출 + 팀장이 메일 발송 = 사이클 완료
- 13:00에 미제출자가 존재하면 메일 불가 확인
- 대리 제출 시도 시 `ProxySubmissionError` 확인
- seed admin이 아닌 사용자의 팀장 변경 시도 시 `TeamLeadRegistrationError` 확인
