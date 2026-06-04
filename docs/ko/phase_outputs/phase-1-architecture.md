# Phase 1 아키텍처 요약

## 개요

Teams 주간 보고 자동화 프로젝트의 Phase 1은 아키텍처 설계 및 주요 결정사항 확정을 완료했다. 본 문서는 확정된 아키텍처와 8개의 기술 결정(ADR-001~008), 7개의 보안 결정(ADR-SEC-001~007)을 종합하고, Phase 2로의 핸드오프 지점을 명시한다.

---

## 1. 확정 결정사항: FastAPI (Python 3.12+)

### 백엔드 프레임워크
- **런타임:** FastAPI (Python 3.12+)
- **ORM:** SQLAlchemy 2.x (async) + Alembic (마이그레이션)
- **LLM SDK:** Anthropic anthropic-sdk (Claude Sonnet)
- **검증:** Pydantic v2

### 선택 근거
- Anthropic Python SDK는 LLM 통합의 가장 자연스러운 인터페이스
- msgraph-sdk-python은 Python-first 설계로 Graph API 호출이 명확함
- async/await 네이티브 지원으로 높은 동시성 처리
- Pydantic 모델이 데이터 검증과 직렬화를 동시에 해결

### 배제된 선택지
- Node.js: msgraph-sdk-js가 후발 지원, LLM SDK 에코시스템 약함
- Go: Python LLM SDK 없음, msgraph-sdk-go는 대기열(queue) 개념 부족

---

## 2. 5층 컴포넌트 아키텍처

### Layer 1: Teams 어댑터 (`src/adapters/teams/`)

**bot_handler.py**
- BotFrameworkAdapter 초기화 및 Activity 라우팅
- JWT 검증 (필수 전제조건, ADR-SEC-007)
- 채널 ID 추출 및 검증

**task_module.py**
- Task Module fetch 핸들러: 보고 폼 HTML 또는 팀장 등록 폼 반환
- Task Module submit 핸들러: FormData 파싱 및 서비스 계층 호출

**adaptive_cards.py**
- 6가지 카드 템플릿 정의 (JSON 스키마, Phase 2에서 최종 정의)
- Card action invoke 핸들러

**notification_jobs.py**
- 채널에 주입(proactive) 메시지 전송
- 목 10:00, 13:00 예정된 알림 실행

### Layer 2: API/라우팅 (`src/api/routes/`)

**bot.py**
- `POST /api/messages` — Bot Framework 진입점
- Activity 타입별 라우팅 (message, invoke, ...)

**reports.py**
- `POST /api/reports/submit` — 개인 보고 제출
- `POST /api/reports/aggregate` — 팀 보고 취합 (팀장 전용)
- `POST /api/reports/revise` — 보고 수정 요청
- `GET /api/reports/{report_id}` — 보고 상세 조회

**scheduler.py**
- `POST /internal/scheduler/reminder` — Thu 10:00 (Cloud Scheduler)
- `POST /internal/scheduler/deadline` — Thu 13:00 (Cloud Scheduler)
- HMAC-SHA256 검증 (ADR-004)

**health.py**
- `GET /health` — liveness 프로브

**auth.py**
- `GET /auth/callback?code=...&state=...` — OAuth 콜백
- PKCE 검증, 토큰 저장

### Layer 3: 서비스 계층 (`src/services/`)

**reports/submission_service.py**
- `submit(channel_id, owner_aad_id, week_key, content) → PersonalReport`
- 마감 후 제출 감지 → 이벤트 발행
- ADR-006: owner_aad_id 검증

**reports/aggregation_service.py**
- `aggregate(channel_id, week_key) → TeamReport`
- LLM 호출 (generation_service 위임)
- 상태 전이 처리

**reports/deadline_service.py**
- `check_deadline(channel_id, week_key) → (mode: AUTO|MANUAL, missing_reporters: List[str])`
- 목 13:00 스케줄러 호출 진입점

**reports/revision_service.py**
- `request_revision(channel_id, report_id, feedback) → void`
- 카드 업데이트 및 채널 알림

**mail/draft_service.py**
- `draft_team_report(channel_id, team_report_id) → DraftMail`
- 메일 초안 생성, Graph API POST /me/messages

**mail/send_service.py**
- `send_team_report(channel_id, team_report_id, actor_aad_id) → Mail`
- 삼중 게이트 검증 (ADR-SEC-003)
- Graph API POST /me/messages/{id}/send

**llm/generation_service.py**
- `generate_aggregation(personal_reports: List[str]) → str`
- Anthropic SDK 호출

**acl/team_lead_service.py**
- `register_team_lead(channel_id, user_aad_id) → ChannelConfig`
- 부트스트랩 검증 (ADR-008)
- 전이 검증 (기존 채널만)

### Layer 4: 도메인/DB (`src/domain/`)

**models/** — SQLAlchemy ORM (8개 엔티티)
1. `ChannelConfig` — 채널 메타데이터, 팀장 OID, week_key
2. `ChannelReportTarget` — 채널 내 보고 대상자 (OID 리스트)
3. `ReportSlot` — 대상자별 보고 슬롯 (owner_aad_id, week_key)
4. `PersonalReport` — 개인 보고 (content, status: DRAFT|SUBMITTED|REVISED)
5. `TeamReport` — 팀 보고 (aggregated_content, status: COLLECTING|AUTO_AGGREGATING|MANUAL_PENDING|AWAITING_APPROVAL|MAIL_SENT)
6. `Mail` — 메일 객체 (graph_message_id, status: DRAFT|SENT|CANCELLED)
7. `Token` — OAuth 토큰 메타데이터 (team_lead_aad_id, expires_at) [실제 토큰은 Secret Manager]
8. `AuditLog` — 보안 감시 로그

**repositories/**
- `ChannelScopedRepository` — 기본 클래스, 모든 쿼리에 channel_id 필수 (ADR-002)
- `PersonalReportRepository`
- `TeamReportRepository`
- `ChannelConfigRepository`
- `MailRepository`

**enums.py**
- `AggregationMode` = AUTO | MANUAL
- `ReportStatus` = DRAFT | SUBMITTED | REVISED
- `TeamReportStatus` = COLLECTING | AUTO_AGGREGATING | MANUAL_PENDING | AWAITING_APPROVAL | MAIL_SENT
- `TeamReportStatusEnum` 추가 상태들

### Layer 5: 인프라 (`infra/`)

**scheduler/** — Cloud Scheduler 설정 (Terraform/JSON)
- Reminder job: Thu 10:00 KST
- Deadline job: Thu 13:00 KST
- POST target, X-Scheduler-Sig HMAC 헤더

**graph_client.py**
- `GraphAuthProvider` — OAuth 플로우 (PKCE + state)
- Token 저장소: GCP Secret Manager
- Retry 로직: 지수 백오프 (500ms, 2x, max 3회), circuit breaker (5회 실패 후)

**db.py**
- async SQLAlchemy engine 설정
- Alembic 마이그레이션 경로

---

## 3. 취합 상태 머신

### 6가지 상태
1. **COLLECTING** — 제출 대기 중
2. **AUTO_AGGREGATING** — 13:00 제출 완료, LLM 취합 중
3. **MANUAL_PENDING** — 마감 후 지연 제출 있음, 팀장 수동 취합 대기
4. **AWAITING_APPROVAL** — LLM 취합 완료, 팀장 승인/메일 대기
5. **MAIL_SENT** — 메일 발송 완료, 최종 상태
6. (암묵적) **DEADLINE_PASSED** — 13:00 도과 후 상태 고정 (전이 불가)

### 7가지 전이

| From | To | Trigger | 조건 |
|---|---|---|---|
| COLLECTING | AUTO_AGGREGATING | deadline_service.check_deadline() at Thu 13:00 | 전원 제출 |
| COLLECTING | MANUAL_PENDING | submission_service.submit() | submitted_after_deadline=true |
| AUTO_AGGREGATING | AWAITING_APPROVAL | LLM 취합 완료 | aggregation_service 콜백 |
| MANUAL_PENDING | MANUAL_PENDING | submission_service.submit() | 또 다른 지연 제출 |
| MANUAL_PENDING | AWAITING_APPROVAL | aggregation_service.aggregate() 팀장 호출 | 팀장 수동 취합 |
| AWAITING_APPROVAL | MAIL_SENT | mail_send_service.send() | 메일 발송 성공 |
| 모든 상태 | AWAITING_APPROVAL | revision_service.request_revision() | 승인 후 피드백 |

### 상태 다이어그램

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

## 4. Teams 통합

### 4가지 봇 명령

| 명령어 | 행위자 | UI | 엔드포인트 |
|---|---|---|---|
| 이번 주 보고 작성 | 팀원 | Task Module | POST /api/messages (invoke, action=submit) |
| 팀 주간 보고 취합 | 팀장 | Adaptive Card | POST /api/messages (invoke, action=aggregate) |
| 보고 대상 지정 | 팀장 | Task Module | POST /api/messages (invoke, action=assign_targets) |
| 팀장 등록 | 관리자/본인 | Adaptive Card | POST /api/messages (invoke, action=register_lead) |

### 6가지 Adaptive Card 템플릿

1. **personal_report_preview_card**
   - 제출 후 개인 보고 미리보기
   - 내용 요약, 제출 시각, 상태 배지
   - "수정 요청" 액션 가능

2. **team_lead_status_card_state1_pending**
   - COLLECTING 상태에서 미제출자 목록
   - "N명 미제출, 메일 불가 상태"
   - 팀장이 정기적으로 카드 업데이트 구독

3. **team_lead_status_card_state2_all_submitted**
   - COLLECTING 또는 AUTO_AGGREGATING에서 전원 제출
   - "전원 제출 완료, 취합 버튼 활성화"
   - 늦은 제출이 발생하면 상태 1로 역전

4. **aggregate_report_preview_card**
   - LLM 취합 완료 후 팀장 미리보기
   - "승인" 또는 "수정 요청" 액션

5. **scheduled_reminder_card_thu_1000**
   - 목 10:00 KST 정기 알림
   - "아직 보고 미제출" 체크
   - 제출 버튼 포함

6. **scheduled_deadline_card_thu_1300**
   - 목 13:00 KST 마감 알림
   - "자동 취합 시작" 또는 "수동 취합 대기" 안내

---

## 5. Graph API / OAuth 설계

### OAuth 플로우: Authorization Code + PKCE

1. **팀장 초기화**
   - `GET /auth/start?channel_id=...` — state (128-bit entropy), PKCE code_challenge 생성
   - 3분 TTL state 저장
   - Microsoft OAuth 리다이렉트: `https://login.microsoftonline.com/.../oauth2/v2.0/authorize?...`

2. **콜백**
   - `GET /auth/callback?code=...&state=...`
   - state 검증, code_verifier PKCE 검증
   - POST `/token` — Graph API, Authorization Code + PKCE → access_token + refresh_token

3. **토큰 저장소**
   - GCP Secret Manager (채널별 팀장 OID 단위)
   - `graph-access-token-{oid}` — 만료 시간 포함
   - `graph-refresh-token-{oid}` — 갱신용
   - `graph-token-metadata-{oid}` — 메타데이터 (scopes, issued_at)

4. **토큰 갱신**
   - Automatic: graph_client.ensure_valid_token(team_lead_aad_id)
   - Atomic write: 새 refresh token을 Secret Manager에 먼저 쓴 후 사용 (ADR-SEC-004)
   - 쓰기 실패 시 operation abort, 재인증 요구

### 메일 엔드포인트

| 작업 | 메서드 | 엔드포인트 | 권한 |
|---|---|---|---|
| 초안 작성 | POST | /me/messages | Mail.Send |
| 초안 수정 | PATCH | /me/messages/{message-id} | Mail.Send |
| 메일 발송 | POST | /me/messages/{message-id}/send | Mail.Send |
| 메일 삭제 | DELETE | /me/messages/{message-id} | Mail.Send |

### 권한 범위
- `Mail.Send` (delegated only)
- `User.Read` (profile, display name)

### 재시도 정책
- 지수 백오프: 500ms 초기, 2x 배수, 최대 3회
- Circuit breaker: 5회 연속 실패 후 10분 차단
- 429 (throttling): Retry-After 헤더 존중

---

## 6. 보안 아키텍처

### Bot Framework JWT 검증 (ADR-SEC-007)
- 모든 `/api/` 및 `/internal/` 엔드포인트 이전에 필수 실행
- Production: Microsoft 공개 키로 서명 검증
- Development: 암호 기반 검증만 허용
- 건너뛸 수 없는 middleware

### 채널 격리 (ADR-SEC-005)
- **Partition Key:** channel_id (Bot Framework Activity에서만 추출)
- **ORM 강제:** ChannelScopedRepository 기본 클래스
- **검증:** 모든 service 함수에서 channel_id를 첫 번째 인수로 필수
- **크로스 채널 시도:** 감시 로그 + 거부

### 대리 제출 금지 (ADR-SEC-006)
- **불변:** activity.from.aadObjectId == PersonalReport.owner_aad_id
- **검증 위치:** submission_service.submit() 내
- **위반 시:** 403 Forbidden + 감시 로그

### 삼중 게이트 메일 발송 (ADR-SEC-003)
- **Gate 1:** TeamReport.status == AWAITING_APPROVAL
- **Gate 2:** 모든 ChannelReportTarget이 해당 주의 PersonalReport를 보유
- **Gate 3:** 행위자 AAD ID == ChannelConfig.team_lead_aad_id
- **검증:** 메일 발송 직전 서버에서 재검증 (카드 상태 재현 공격 방지)

### 스케줄러 인증 (ADR-004)
- **방식:** HMAC-SHA256 (X-Scheduler-Sig 헤더)
- **Secret:** SCHEDULER_HMAC_SECRET 환경 변수 (Secret Manager에 저장)
- **경로:** /internal/* (reverse proxy에서도 제한)

### Delegated-Only OAuth (ADR-SEC-001)
- **정책:** Graph API 호출에 application permissions 영구 금지
- **검증:** CI lint rule (code review gate)
- **결과:** 봇의 접근 범위가 팀장의 동의한 메일함만으로 제한

### 팀장 등록 이중 게이트 (ADR-SEC-002)
- **조건:** INITIAL_ADMIN_USER_IDS (환경 변수) 또는 자가 등록
- **ID 출처:** Bot Framework Activity만 (카드 payload 제외)
- **부트스트랩 실패:** 환경 변수 누락 시 시작 실패 (미설정 감시)

### Refresh Token 원자성 (ADR-SEC-004)
- **동작:** 새 token을 Secret Manager에 먼저 쓰고 사용
- **실패 시:** operation abort, 재인증 요구
- **결과:** 1:1 토큰 버전 일관성

---

## 7. DB 엔티티 및 채널 격리

### 8개 SQLAlchemy ORM 모델

#### 1. ChannelConfig
```
- id (PK, UUID)
- channel_id (UK, indexed)
- team_name (str)
- team_lead_aad_id (str, nullable — 미등록)
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

### 채널 격리 강제 메커니즘

**ChannelScopedRepository 기본 클래스**
```python
class ChannelScopedRepository:
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        # 항상 channel_id를 WHERE 절에 포함
        ...

    async def find_all(self, channel_id: str) -> List[T]:
        # channel_id 없는 조회 불가능 (메서드 시그니처에 필수)
        ...
```

**Service 계층 검증**
```python
async def submit(self, channel_id: str, owner_aad_id: str, ...):
    # 첫 번째 인수는 항상 channel_id
    # Activity에서만 추출 (신뢰할 수 있는 출처)
```

**결과:**
- 실수로도 크로스 채널 조회 불가능
- ORM 쿼리가 자동으로 channel_id 필터링
- 감시 로그는 시도된 크로스 채널 접근 기록

---

## 8. 스케줄러 설계

### Cloud Scheduler 작업

#### 1. Reminder Job (목 10:00 KST)
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

**응답 처리:**
- notification_jobs.send_reminder_cards() 호출
- 모든 채널의 모든 팀원에게 "아직 보고 미제출" 카드 발송
- 기존 카드 업데이트 가능 (Teams adaptive card refresh token)

#### 2. Deadline Job (목 13:00 KST)
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

**응답 처리:**
- deadline_service.check_deadline(channel_id, week_key) 호출 (각 채널)
- 모든 팀원 제출 완료 → TeamReport 상태를 AUTO_AGGREGATING으로 전이
  - aggregation_service.aggregate() async 작업 시작
  - LLM 취합 완료 시 AWAITING_APPROVAL으로 자동 전이
  - 팀장에게 "취합 완료, 승인 대기" 카드 발송
- 지연 제출 있음 → TeamReport 상태를 MANUAL_PENDING으로 유지
  - 팀장에게 "N명 지연, 수동 취합 필요" 카드 발송

### Late Submit Event Hook

**트리거 위치:** `submission_service.submit()` 내, `submitted_after_deadline=true` 감지 시

**처리:**
1. 이벤트 발행 (in-process async event bus)
2. 이벤트 콜백: TeamReport 상태 재계산
3. 미제출자 다시 집계
4. 팀장 카드 상태 업데이트 (채널 proactive message로 기존 카드 refresh 또는 새 카드 발송)
5. remaining_missing == 0이면 상태를 "전원 제출 완료" 카드로 변경

---

## 9. 미결 사항 (Phase 2로 이관)

### 1. DB 스키마 상세 정의
- [ ] 각 모델의 인덱스 전략 (FK, UK, covering index)
- [ ] 파티션 키 고려 (cloud-native DB라면 partition by channel_id)
- [ ] 감시 로그 보존 정책 (30일? 90일?)

### 2. Adaptive Card JSON 템플릿
- [ ] personal_report_preview_card 상세 스키마
- [ ] team_lead_status_card_state1_pending 동적 내용 (미제출자 목록)
- [ ] team_lead_status_card_state2_all_submitted 액션 바인딩
- [ ] aggregate_report_preview_card 수정 요청 피드백 UI
- [ ] scheduled_reminder_card_thu_1000 보고 작성 버튼
- [ ] scheduled_deadline_card_thu_1300 자동/수동 모드 표시

### 3. LLM 프롬프트 설계
- [ ] Persona: 팀장, 전사 이해도 높은 편집자
- [ ] Input format: 개인 보고 목록 (JSON 구조)
- [ ] Output format: 마크다운 섹션별 요약
- [ ] Safety: 민감 정보 필터링 (이메일 등)
- [ ] Token 한계: 최대 input+output (모델별 제한)

### 4. 메일 To/CC 설정 UX
- [ ] 팀장 보고서 작성 시 수신자 지정 가능?
- [ ] 기본값: 본인(팀장) + 상위 보고 대상자?
- [ ] Task Module 확장 또는 Adaptive Card?

### 5. 마감 후 제출 시간 한계
- [ ] 목 13:00 이후 최대 몇 시간까지 지연 제출 허용?
- [ ] 관리 정책: 무한정? 금요일 자정? 다음 주 월요일?
- [ ] 자동 취합 후 수동 취합 최대 횟수?

### 6. Teams 앱 패키지 최종 작성
- [ ] manifest.json — bot ID, scopes, activity types
- [ ] 아이콘, 소개 텍스트
- [ ] 명령어 목록 및 설명

### 7. Local 개발 환경 구성
- [ ] Docker Compose (fastapi, postgres, redis)
- [ ] ngrok 또는 devtunnel 설정
- [ ] Teams 앱 side-load 지침
- [ ] Mock scheduler 또는 manual trigger endpoint

---

## 10. Phase 2 핸드오프

### 전달 물품
1. **아키텍처 문서** (본 문서)
2. **15개 ADR** (기술 + 보안 결정사항)
3. **프로젝트 결정사항** (docs/ko/05_project_decisions.md 기존)
4. **요구사항 스펙** (docs/ko/01_requirements_spec.md 확정)

### Phase 2 작업 순서 (추천)
1. **인프라 준비** (2-3일)
   - GCP 프로젝트 설정 (Secret Manager, Cloud Scheduler)
   - PostgreSQL 프로비저닝 (또는 Cloud SQL)
   - 로컬 개발 환경 (Docker + ngrok)

2. **DB 스키마 + Alembic** (3-4일)
   - SQLAlchemy 모델 상세 구현
   - 마이그레이션 작성 및 테스트
   - 채널 격리 enforcement test

3. **OAuth 및 Graph Client** (3-4일)
   - PKCE flow 구현
   - Secret Manager 저장소
   - Token refresh 및 circuit breaker

4. **Service 계층** (5-7일)
   - submission_service, aggregation_service, deadline_service
   - LLM 프롬프트 및 generation_service
   - mail_draft_service, mail_send_service (triple-gate)

5. **API 라우팅 + Teams 어댑터** (4-5일)
   - bot_handler, task_module, adaptive_cards
   - 6개 카드 템플릿 (JSON)
   - Bot Framework middleware 및 JWT 검증

6. **스케줄러 및 알림** (2-3일)
   - Cloud Scheduler 통합
   - notification_jobs
   - Late submit event hook

7. **테스트 + 문서화** (5-7일)
   - Unit test (service, repo)
   - Integration test (API endpoints, OAuth)
   - E2E test (Teams 채널)
   - API 문서 (Swagger/OpenAPI)

### 의존성 확인
- [ ] Azure AD 테넌트 (Teams, Microsoft Graph)
- [ ] GCP 프로젝트 (Secret Manager, Cloud Scheduler, 또는 CloudRun)
- [ ] 개발자 Teams 테스트 환경
- [ ] MongoDB 또는 PostgreSQL (선택)
- [ ] Anthropic API 키

### 위험 요소
- **DateTime 관리:** 각 시스템의 타임존이 혼동되지 않도록 주의 (Python zoneinfo, UTC 저장)
- **State Machine:** 마감 후 상태 전이 논리 복잡도 (충분한 test coverage)
- **OAuth Token Refresh:** 동시성 상황에서 double-refresh 방지
- **Mail Send Gate:** 3개 조건 재검증 락(lock) 경합(contention) 시 deadlock 주의

---

## 11. 용어 정의

| 용어 | 뜻 |
|---|---|
| **week_key** | ISO 8601 주 번호, e.g., "2026-W23" |
| **channel_id** | Teams 채널 ID (Bot Framework Activity에서 제공) |
| **team_lead_aad_id** | Azure AD Object ID (팀장) |
| **owner_aad_id** | 개인 보고 소유자의 AAD Object ID |
| **aggregation_mode** | AUTO (13:00 전원 제출 완료) 또는 MANUAL (지연 제출 있음) |
| **submitted_after_deadline** | 목 13:00 이후 제출 여부 |
| **partition key** | DB 쿼리에서 항상 필요한 channel_id |
| **ChannelScopedRepository** | 모든 repository의 기본 클래스, channel_id 강제 |
| **triple-gate** | 메일 발송 전 3가지 조건 검증 (상태 + 완성도 + 권한) |
| **PKCE** | Proof Key for Code Exchange (OAuth CSRF 방지) |
| **Adaptive Card** | Microsoft Teams 카드 UI (JSON 기반) |
| **Task Module** | Teams 내 모달 폼 (Task fetch/submit) |

---

## 12. 참고 문서

- [01_requirements_spec.md](../01_requirements_spec.md) — 요구사항 확정
- [02_required_environment.md](../02_required_environment.md) — 환경 및 권한
- [03_agent_roles.md](../03_agent_roles.md) — Agent 역할 정의
- [05_project_decisions.md](../05_project_decisions.md) — MVP 핵심 결정
- [adr/](../adr/) — 15개 ADR (기술 + 보안)
