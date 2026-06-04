# Phase 2 백엔드 구현 산출물

작성일: 2026-06-04
담당: @backend-developer

---

## 1. 개요

Teams 주간 보고 자동화 프로젝트의 백엔드 핵심 레이어를 구현하였다.
FastAPI(Python 3.12+), SQLAlchemy 2.x async, Alembic, pydantic-settings 기반이며
Phase 1 ADR의 모든 확정 결정사항을 준수한다.

---

## 2. 생성된 파일 목록

### 프로젝트 설정
| 파일 | 설명 |
|---|---|
| `src/__init__.py` | 백엔드 패키지 루트 |
| `src/main.py` | FastAPI 앱, 라우터 마운트, lifespan 스타트업 검증 |
| `requirements.txt` | 전체 의존성 (fastapi, sqlalchemy, alembic, anthropic 등) |
| `.env.example` | 필수 환경 변수 전체 목록 및 설명 |

### 도메인 모델 (`src/domain/`)
| 파일 | 설명 |
|---|---|
| `src/domain/__init__.py` | 도메인 레이어 패키지 |
| `src/domain/enums.py` | `AggregationMode`, `ReportStatus`, `TeamReportStatus` |
| `src/domain/models/base.py` | `DeclarativeBase`, `TimestampMixin` (UTC created_at/updated_at) |
| `src/domain/models/channel_config.py` | `ChannelConfig` — 채널별 설정, team_lead_aad_id |
| `src/domain/models/channel_report_target.py` | `ChannelReportTarget` — 보고 대상 멤버 |
| `src/domain/models/personal_report.py` | `PersonalReport` — `submitted_after_deadline` 포함 |
| `src/domain/models/team_report.py` | `TeamReport` — `aggregation_mode` 열거형 포함 |
| `src/domain/models/revision_history.py` | `RevisionHistory` — 취합본 수정 이력 |
| `src/domain/models/mail_draft.py` | `MailDraft` — Graph API 메일 페이로드 |
| `src/domain/models/audit_log.py` | `AuditLog` — 불변 이벤트 로그 |
| `src/domain/models/reminder_log.py` | `ReminderLog` — 알림 발송 기록 |

### 인프라 (`src/infra/`)
| 파일 | 설명 |
|---|---|
| `src/infra/__init__.py` | 인프라 레이어 패키지 |
| `src/infra/config.py` | `Settings` (pydantic-settings), `get_settings()` 캐시 |
| `src/infra/db.py` | async 엔진, `async_sessionmaker`, `get_db` 의존성, `create_tables()` |

### 리포지토리 (`src/domain/repositories/`)
| 파일 | 설명 |
|---|---|
| `src/domain/repositories/__init__.py` | 리포지토리 export |
| `src/domain/repositories/base.py` | `ChannelScopedRepository` — `_require_channel_id` 강제 |
| `src/domain/repositories/channel_config_repo.py` | `ChannelConfigRepository` |
| `src/domain/repositories/personal_report_repo.py` | `PersonalReportRepository` |
| `src/domain/repositories/team_report_repo.py` | `TeamReportRepository` |

### 서비스 (`src/services/`)
| 파일 | 설명 |
|---|---|
| `src/services/__init__.py` | 서비스 레이어 패키지 |
| `src/services/reports/__init__.py` | 보고 서비스 패키지 |
| `src/services/reports/week_utils.py` | `get_week_deadline()`, `week_key_from_dt()`, `is_after_deadline()` |
| `src/services/reports/submission_service.py` | `SubmissionService.submit()` — 프록시 차단, 지각 감지 |
| `src/services/reports/aggregation_service.py` | `AggregationService` — 상태 머신 전환, `can_send_mail()` |
| `src/services/reports/deadline_service.py` | `DeadlineService.run()` — AUTO/MANUAL 판정, 멱등성 보장 |
| `src/services/acl/__init__.py` | ACL 서비스 패키지 |
| `src/services/acl/team_lead_service.py` | `TeamLeadService` — 팀장 등록, `validate_team_lead()` |

### API 라우트 (`src/api/`)
| 파일 | 설명 |
|---|---|
| `src/api/__init__.py` | API 레이어 패키지 |
| `src/api/dependencies.py` | `inject_channel_config`, `verify_scheduler_hmac`, `verify_hmac_signature` |
| `src/api/routes/__init__.py` | 라우트 패키지 |
| `src/api/routes/health.py` | `GET /health` — DB 프로브 포함 |
| `src/api/routes/scheduler.py` | `POST /internal/scheduler/reminder`, `POST /internal/scheduler/deadline` |

### Alembic 마이그레이션
| 파일 | 설명 |
|---|---|
| `alembic.ini` | Alembic 설정 (DB URL은 Settings에서 주입) |
| `alembic/env.py` | async 호환 env, ORM 모델 자동 감지 |
| `alembic/versions/.gitkeep` | 마이그레이션 버전 디렉터리 초기화 |

---

## 3. 핵심 비즈니스 규칙 구현 내역

### 3.1 채널 ID 격리 (Channel Isolation)
- 모든 테이블에 `channel_id` 파티션 키 컬럼 존재
- `ChannelScopedRepository._require_channel_id()` — None/빈 값 시 즉시 `ValueError` 발생
- 모든 쿼리에 `WHERE channel_id = ?` 조건 강제

### 3.2 프록시 제출 차단 (No Proxy Submission)
`submission_service.submit()` 첫 번째 가드:
```python
if actor_aad_id != target_aad_id:
    raise ProxySubmissionError(...)
```
`actor_aad_id`는 반드시 Bot activity의 `activity.from.aadObjectId`에서 추출해야 한다.

### 3.3 마감 후 제출 (Post-Deadline Submit)
- `is_after_deadline(week_key)` 로 판정
- 마감 후 제출 시 `status = LATE_SUBMITTED`, `submitted_after_deadline = True`
- TeamReport가 `MANUAL_PENDING` 상태일 때만 허용 (또는 경쟁 조건 대비 `COLLECTING`)
- 팀장 대리 제출 불가 — `actor_aad_id == target_aad_id` 검증이 항상 선행

### 3.4 메일 발송 차단 조건
`AggregationService.can_send_mail()`:
- TeamReport가 `AWAITING_APPROVAL` 상태여야 함
- PENDING 상태 멤버가 한 명이라도 있으면 `(False, "Cannot send mail: N non-submitter(s)")` 반환

### 3.5 상태 머신 전환
```
COLLECTING → (Thu 13:00 deadline_service.run())
    ├─ 전원 제출 → AUTO_AGGREGATING → (aggregation_service.evaluate()) → AWAITING_APPROVAL
    └─ 미제출 존재 → MANUAL_PENDING → (모든 지각 제출 완료 시 on_late_submit()) → AWAITING_APPROVAL
                                                                           ↓
                                                                      MAIL_SENT
```

### 3.6 스케줄러 HMAC 인증
- `X-Scheduler-Sig`: `HMAC-SHA256("{timestamp}:{body}")` hex digest
- `X-Scheduler-Ts`: 서명에 사용된 Unix 타임스탬프
- `verify_hmac_signature()` — `hmac.compare_digest()` 로 타이밍 안전 비교

### 3.7 주간 마감 시각 계산
`get_week_deadline(week_key) -> datetime (UTC)`:
- ISO 주차(week_key)의 목요일 13:00 Asia/Seoul을 UTC로 변환
- 예: `"2026-W23"` → `2026-06-04T04:00:00+00:00`

### 3.8 INITIAL_ADMIN_USER_IDS 스타트업 검증
`src/main.py` lifespan에서:
```python
if not settings.initial_admin_user_ids:
    raise RuntimeError("INITIAL_ADMIN_USER_IDS is missing or empty.")
```
빈 값이면 애플리케이션 시작 자체가 실패한다.

---

## 4. 필수 환경 변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `DATABASE_URL` | 필수 | SQLAlchemy async URL (asyncpg 또는 aiosqlite) |
| `AZURE_TENANT_ID` | 필수 | Azure AD 테넌트 ID |
| `AZURE_CLIENT_ID` | 필수 | Azure AD 앱 클라이언트 ID |
| `AZURE_CLIENT_SECRET` | 필수 | Azure AD 앱 클라이언트 시크릿 |
| `BOT_APP_ID` | 필수 | Bot Framework 앱 ID |
| `BOT_APP_PASSWORD` | 필수 | Bot Framework 앱 패스워드 |
| `SCHEDULER_HMAC_SECRET` | 필수 | 스케줄러 HMAC-SHA256 공유 시크릿 |
| `INITIAL_ADMIN_USER_IDS` | 필수 | 초기 팀장 시드 (쉼표 구분 AAD Object ID 목록) |
| `ANTHROPIC_API_KEY` | 필수 | Anthropic API 키 |
| `ANTHROPIC_MODEL` | 선택 | 사용할 모델 (기본: `claude-sonnet-4-6`) |
| `APP_TIMEZONE` | 선택 | 마감 계산 타임존 (기본: `Asia/Seoul`) |
| `DEBUG` | 선택 | `true` 시 `/docs` 활성화 (기본: `false`) |
| `LOG_LEVEL` | 선택 | 로그 레벨 (기본: `INFO`) |

---

## 5. 로컬 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일에서 실제 값 입력

# 3. DB 마이그레이션 (처음 실행 시)
alembic upgrade head

# 4. 개발 서버 실행
uvicorn src.main:app --reload --port 8000

# 5. 헬스 체크
curl http://localhost:8000/health
```

### SQLite 개발 환경 (DB 없이 빠른 시작)
`.env` 파일에서:
```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

---

## 6. Alembic 마이그레이션 명령

```bash
# 현재 상태 확인
alembic current

# 최신 마이그레이션 적용
alembic upgrade head

# 자동 마이그레이션 생성 (ORM 변경 후)
alembic revision --autogenerate -m "add column X to table Y"

# 한 단계 롤백
alembic downgrade -1
```

---

## 7. 향후 연계 지점

- `src/adapters/teams/` — Bot 핸들러에서 `SubmissionService.submit()` 호출 시 `actor_aad_id`를 반드시 `activity.from.aadObjectId`로 전달
- `src/services/mail/send_service.py` — 메일 발송 전 `AggregationService.can_send_mail()` 호출 필수
- 외부 스케줄러 — `POST /internal/scheduler/reminder` (목 01:00 UTC), `POST /internal/scheduler/deadline` (목 04:00 UTC) 호출, HMAC 서명 첨부
