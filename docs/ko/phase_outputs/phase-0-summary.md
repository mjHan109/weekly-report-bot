# Phase 0 발견 요약 (Discovery Summary)

## 1. 목적 (Purpose)
Microsoft Teams Bot으로 채널별 주간 보고 작성·취합·메일 발송을 자동화하는 MVP 범위를 확정하고, Phase 1 설계·개발을 위한 기술 기반을 마련한다.

## 2. 확정된 비즈니스 규칙 (Confirmed Business Rules)

### 2.1 보고 마감 및 알림 일정
- **마감:** 매주 목요일(Thu) 13:00 KST
- **목 10:00:** 미제출자 채널 알림
- **목 13:00:** 취합 및 알림 (다음 참조)

### 2.2 목 13:00 분기점
- **자동 취합 조건:** 지정된 모든 보고 대상이 13:00 이전에 제출
  - → 자동 취합 실행 + 팀장 확인 카드 발송
- **수동 취합 조건:** 미제출자 또는 지연 제출자 발생
  - → 채널 공지 (수동 취합 요청) + 팀장 대기 상태 카드 발송

### 2.3 지연 제출 규칙
- **자기 제출만 허용:** 미제출자 본인만 13:00 이후 제출 가능
  - 팀장의 대리 제출 **절대 금지** (ANY 상황)
- **취합 제약:** 지연 제출자가 있으면 수동 취합만 가능

### 2.4 메일 발송 조건
- **차단 조건:** 미제출자가 1명이라도 존재하면 메일 발송 불가
- **발송 조건:** 모든 보고 제출 + 취합 완료 + 팀장 승인
- 알림: Thu 10:00, 13:00 채널 공지 (미제출 시 메일 불가 안내)

### 2.5 팀장 등록 및 보고 대상 지정
- **팀장 등록:** INITIAL_ADMIN_USER_IDS 환경변수 사용자 OR 팀장 자신이 등록
- **보고 대상 지정:** 팀장이 채널별로 지정된 인원 명시

### 2.6 보고 기간
- 이전 주 목요일 13:00:01 ~ 현재 주 목요일 13:00:00 KST (한국 시간)

## 3. 사용자 플로우 (User Flows)

### Flow 1: 팀원 정시 제출
1. 팀원이 목 13:00 이전에 주간 보고 작성
2. Bot Task Module에서 보고서 입력
3. DB 저장 (submitted_after_deadline = false)
4. 팀원 확인 메시지

### Flow 2: 팀원 지연 자기 제출
1. 팀원이 목 13:00 이후 보고서 작성
2. Bot Task Module에서 보고서 입력 (본인만 가능)
3. DB 저장 (submitted_after_deadline = true)
4. 팀원 확인 메시지

### Flow 3: 팀장 자동 취합 & 메일 발송
1. 목 13:00: Cloud Scheduler 트리거
2. 모든 보고 대상 제출 확인
3. 조건 충족 → 자동 취합, TeamReport(aggregation_mode=auto) 저장
4. 팀장 Adaptive Card 발송 (채널/DM)
5. 팀장 "메일 발송" 버튼 클릭
6. 메일 생성 + Graph API 발송

### Flow 4: 팀장 수동 취합 & 메일 발송
1. 목 13:00: 미제출자 또는 지연 제출자 있음
2. 채널 공지 (수동 취합 안내)
3. 팀장 Adaptive Card 발송 (상태: 취합 대기)
4. 팀장이 필요시 직접 취합 → TeamReport(aggregation_mode=manual) 저장
5. 팀장 "메일 발송" 버튼 클릭
6. 메일 생성 + Graph API 발송

### Flow 5: 팀장 등록
1. INITIAL_ADMIN_USER_IDS 또는 팀장 자신이 /register 명령어 실행
2. Teams User ID, Name, Email 확인
3. DB ChannelConfig 저장 (team_lead_id, team_lead_email)
4. 등록 완료 메시지

### Flow 6: 보고 대상 지정
1. 팀장이 Task Module 또는 Adaptive Card choiceSet 실행
2. 채널 구성원 목록 표시 (다중선택)
3. 선택한 인원 저장 → ChannelReportTarget
4. 확인 메시지

## 4. MVP 범위 (MVP Scope - FR-013~FR-021)

| FR | 제목 | 설명 |
|---|---|---|
| FR-013 | 목 10:00 채널 알림 | 미제출자에게 채널 공지 |
| FR-014 | 팀장 등록 | INITIAL_ADMIN 또는 팀장 자신이 등록 |
| FR-015 | 목 13:00 알림 + 상태 카드 | 자동/수동 취합 상태 팀장에게 전달 |
| FR-016 | 지연 자기 제출 | 미제출자 본인만 13:00 이후 제출 (팀장 대리 금지) |
| FR-017 | 미제출 시 메일 차단 | 1명이라도 미제출 → 메일 발송 불가 |
| FR-018 | 보고 대상 지정 | 팀장이 채널별 보고 대상 지정 |
| FR-019 | 자동 취합 | 모든 보고 대상 13:00 이전 제출 → 자동 취합 |
| FR-020 | 수동 취합 (팀장만) | 미제출/지연 발생 → 팀장이 수동 취합 |
| FR-021 | 팀장 상태 Adaptive Card | 2가지 상태: 자동 취합 완료, 수동 취합 대기 |

## 5. 기술 스택 (Tech Stack)

### 5.1 백엔드
- **프레임워크:** Python FastAPI **또는** Node.js NestJS
  - **주의:** Phase 1에서 반드시 선택 및 고정 필요
  - 결정 후 `05_project_decisions.md`에 기록

### 5.2 데이터베이스
- **프로덕션:** PostgreSQL (Google Cloud SQL)
- **개발:** SQLite

### 5.3 인증 & 그래프 API
- **Bot 인증:** Bot Framework (Teams)
- **메일 발송 인증:** Delegated OAuth + PKCE (Microsoft Graph)
- **Graph 스코프:** openid, profile, email, offline_access, User.Read, Mail.ReadWrite, Mail.Send
- **주의:** 테넌트 관리자 동의(admin consent) 필요

### 5.4 인프라 & 배포
- **서버:** Google Cloud Run (서버리스)
- **DB:** Cloud SQL
- **시크릿:** Secret Manager
- **스케줄링:** Cloud Scheduler (목 13:00, 10:00 트리거)

### 5.5 LLM
- **모델:** Anthropic Claude Sonnet (보고서 생성, 취합 지원)

## 6. DB 엔티티 목록 (DB Entities)

| 엔티티 | 설명 | 주요 필드 |
|---|---|---|
| ChannelConfig | 채널별 팀장, 메일 설정 | channel_id, team_lead_id, team_lead_email, created_at |
| ChannelReportTarget | 채널별 보고 대상자 | channel_id, user_id, user_email, added_at |
| PersonalReport | 팀원 보고서 | channel_id, user_id, report_content, submitted_at, submitted_after_deadline |
| TeamReport | 취합된 팀 보고서 | channel_id, aggregation_mode (auto/manual), aggregated_at, aggregated_by |
| RevisionHistory | 보고서 수정 이력 | report_id, content_diff, revised_at, revised_by |
| MailDraft | 메일 초안 | team_report_id, mail_body, created_at, sent_at |
| AuditLog | 감시 로그 | action, actor, resource, timestamp, details |
| ReminderLog | 알림 이력 | channel_id, reminder_type (10:00/13:00), sent_at |

**총 8개 엔티티** — Phase 2에서 상세 스키마 정의

## 7. 핵심 컴포넌트 (Key Components)

### 7.1 Teams 어댑터 (`src/adapters/teams/`)
- **Bot Handler:** Teams Bot Framework 라우팅, 메시지 수신
- **Task Module:** 보고서 입력 UI (정시/지연 제출 분기)
- **Adaptive Cards:** 팀장 상태 카드 (2 상태), 채널 알림 카드
- **Notification Service:** Thu 10:00, 13:00 채널 공지

### 7.2 보고 서비스 (`src/services/reports/`)
- **Report Lifecycle Manager:** 제출, 지연 제출, 상태 추적
- **Aggregation State Machine:** 자동 취합 vs 수동 취합 로직
- **Deadline Handler:** 목 13:00 분기점 로직
- **Submission Validator:** 보고 대상 여부, 마감 여부 검증

### 7.3 메일 서비스 (`src/services/mail/`)
- **Graph OAuth Handler:** Delegated OAuth + PKCE flow
- **Mail Composer:** 메일 본문 생성 (보고서 기반)
- **Mail Sender:** Graph Mail.Send API 호출
- **Mail Draft Manager:** MailDraft 엔티티 관리

### 7.4 LLM 서비스 (`src/services/llm/`)
- **Prompt Manager:** 프롬프트 템플릿 관리
- **LLM Client:** Anthropic Claude API wrapper
- **Report Generation Helper:** 보고서 작성 조력

### 7.5 API 계층 (`src/api/`)
- **REST Endpoints:** /submit, /aggregate, /send-mail, /register, /set-targets
- **OAuth Callback:** `/auth/callback` (Graph token 수신)
- **ACL Middleware:** 팀장 권한 검증 (aggregate, send-mail)

### 7.6 인프라 (`infra/`)
- **Cloud Scheduler Config:** 목 10:00, 13:00 HTTP POST trigger
- **Cloud Run Deployment:** Dockerfile, 환경변수 설정
- **Secret Manager Integration:** 시크릿 주입

### 7.7 Teams 앱 패키지 (`teams-app/manifest/`)
- **manifest.json:** Bot ID, scopes, commands, messaging extensions
- **Task Module Config:** deeplink 기반 Task Module 호출

## 8. 미결 사항 (Open Questions)

### 8.1 기술 결정 (Phase 1에서 해결)
1. **백엔드 프레임워크:** FastAPI vs NestJS → **반드시 Phase 1에서 선택**
2. **팀장 Adaptive Card 배달:** 채널 공지 vs 1:1 DM → Phase 1 ADR 필요
3. **지연 제출 마감:** 13:00 이후 몇 시간까지 수락? → 비즈니스 정책 결정 필요
4. **Adaptive Card 업데이트:** 제자리 업데이트 (activity ID 저장) vs 재발송 → Phase 1 ADR
5. **보고 대상 지정 UX:** Task Module vs Adaptive Card choiceSet → Phase 1 선택
6. **지연 제출 완료 감지:** Cloud Scheduler만으로 충분? → 보고 서비스 이벤트 훅 필요 검토

### 8.2 구현 정의
- Graph OAuth callback 엔드포인트 상세 설계
- Cloud Scheduler 트리거 페이로드 포맷
- 보고 주기 경계 처리 (정확히 13:00:00 시점)

## 9. 리스크 (Risks)

| Risk ID | 제목 | 설명 | 영향 | 완화책 |
|---|---|---|---|---|
| RISK-01 | 백엔드 프레임워크 미결 | FastAPI vs NestJS 결정 안됨 | 높음 | Phase 1 초반 ADR로 결정 |
| RISK-02 | OAuth 토큰 생명주기 | 팀장 변경 시 토큰 갱신 로직 미정의 | 중간 | Phase 1 설계에서 토큰 갱신 전략 수립 |
| RISK-03 | 지연 제출 완료 감지 | Cloud Scheduler 폴링만으로는 지연 감지 어려움 | 중간 | 보고 서비스 이벤트 훅 추가 검토 |
| RISK-04 | 팀장 카드 배달 채널 | 채널 vs 1:1 DM 결정에 따라 구현 변화 | 낮음 | Phase 1 비즈니스 요구사항 명확화 |
| RISK-05 | Graph 메일 스코프 권한 | Mail.ReadWrite, Mail.Send 관리자 동의 필요 | 중간 | 테넌트 관리자와 사전 협의 |
| RISK-06 | Adaptive Card 업데이트 | 제자리 vs 재발송에 따라 사용자 경험 차이 | 낮음 | Phase 1 UX 검토 후 결정 |
| RISK-07 | 보고 주기 경계 케이스 | 정확히 13:00:00 제출의 타이밍 문제 | 낮음 | 데이터베이스 타임스탬프 정밀도 확보 (millisecond) |
| RISK-08 | INITIAL_ADMIN_USER_IDS 부트스트랩 | 초기 관리자 설정 프로세스 미정의 | 중간 | Phase 1 배포 운영 가이드 작성 |

## 10. Phase 1 핸드오프 (Phase 1 Handoff)

### 10.1 반드시 결정할 사항
- [ ] 백엔드 프레임워크 선택 (FastAPI OR NestJS) → `05_project_decisions.md` 기록
- [ ] 팀장 카드 배달 채널 (채널 vs DM)
- [ ] 지연 제출 마감 시간 (13:00 + N시간)
- [ ] Adaptive Card 업데이트 전략 (제자리 vs 재발송)
- [ ] 보고 대상 지정 UX (Task Module vs choiceSet)

### 10.2 작성할 ADR (Architecture Decision Records)
1. **ADR-001:** Task Module vs Native Form
2. **ADR-002:** Delegated OAuth vs Application OAuth
3. **ADR-003:** Channel ID as Partition Key
4. **ADR-004:** No Team-Lead Proxy Submit Policy
5. **ADR-005:** Cloud Scheduler vs In-Process Cron
6. **ADR-006:** Adaptive Card Update Strategy

### 10.3 생산할 문서 & 산출물
- [ ] Component Architecture Diagram (화면 모형 포함)
- [ ] Graph OAuth Callback Flow (시퀀스 다이어그램)
- [ ] Cloud Scheduler Endpoint 상세 설계
- [ ] DB 엔티티 최종 목록 (Phase 2 스키마 준비)
- [ ] **phase-1-architecture.md** (ko + en 동기화)

### 10.4 Phase 2로 넘길 미결 사항
- DB 상세 스키마 정의 (엔티티 각 필드, 제약조건, 인덱스)
- Graph OAuth 토큰 갱신/만료 처리 로직
- Cloud Scheduler 클라우드 함수 구현 (Python/Node 선택 후)
- Adaptive Card JSON 템플릿
- Test Plan & Test Case 작성
- 배포 & 운영 매뉴얼

---

**Document Status:** Phase 0 Discovery 확정
**Last Updated:** 2026-06-04
**Next Phase:** Phase 1 Architecture & Design ADRs
