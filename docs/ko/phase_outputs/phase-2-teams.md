# Phase 2 산출물 — Teams 통합 엔지니어

작성일: 2026-06-04
역할: @teams-integration-engineer

---

## 1. 개요

Phase 2 MVP에서 Teams 통합 레이어를 구현하였다. Bot Framework CloudAdapter
(botbuilder-core + botbuilder-integration-aiohttp) 기반으로 4개 한국어 명령어,
Task Module 보고서 입력, 6종 Adaptive Card, 채널 알림 스케줄 작업을 모두 구현하였다.

---

## 2. 생성된 파일 목록

### Bot 어댑터 레이어

| 파일 | 역할 |
|---|---|
| `src/adapters/teams/__init__.py` | 패키지 export |
| `src/adapters/teams/bot_handler.py` | BotFrameworkAdapter 연결, on_message_activity, task/fetch, task/submit, adaptiveCard/action 디스패치 |
| `src/adapters/teams/command_router.py` | 한국어 명령어 → 핸들러 라우팅 |

### 명령어 핸들러

| 파일 | 명령어 | ACL |
|---|---|---|
| `src/adapters/teams/handlers/__init__.py` | — | — |
| `src/adapters/teams/handlers/write_report.py` | 이번 주 보고 작성 | 지정 보고 대상자 |
| `src/adapters/teams/handlers/aggregate_report.py` | 팀 주간 보고 취합 | 팀장 전용 |
| `src/adapters/teams/handlers/assign_reporters.py` | 보고 대상 지정 | 팀장 전용 |
| `src/adapters/teams/handlers/register_team_lead.py` | 팀장 등록 | INITIAL_ADMIN 또는 자기 등록 (ADR-008) |

### Task Module

| 파일 | 역할 |
|---|---|
| `src/adapters/teams/task_module/__init__.py` | 패키지 export |
| `src/adapters/teams/task_module/report_form.py` | 보고서 입력 폼 — fetch 페이로드 빌더 + submit 핸들러 |
| `src/adapters/teams/task_module/reporter_select_form.py` | 보고 대상 지정 폼 — fetch 페이로드 빌더 + submit 핸들러 |

### Adaptive Cards

| 파일 | 용도 |
|---|---|
| `src/adapters/teams/cards/__init__.py` | 패키지 export |
| `src/adapters/teams/cards/personal_preview.py` | 제출 후 채널에 표시되는 개인 보고 미리보기 |
| `src/adapters/teams/cards/team_lead_pending.py` | 팀장 상태 카드 — 미제출자 N명, 메일 불가 |
| `src/adapters/teams/cards/team_lead_all_submitted.py` | 팀장 상태 카드 — 전원 제출, 취합 가능 |
| `src/adapters/teams/cards/aggregate_preview.py` | LLM 취합 완료 미리보기 + 메일 승인 버튼 |
| `src/adapters/teams/cards/reminder_1000.py` | 목 10:00 채널 알림 |
| `src/adapters/teams/cards/deadline_1300.py` | 목 13:00 마감 채널 알림 |
| `src/adapters/teams/cards/card_sender.py` | send_card(), update_card(), proactive_send() |

### 알림 스케줄 작업

| 파일 | 역할 |
|---|---|
| `src/adapters/teams/notification_jobs.py` | post_reminder_card(channel_id), post_deadline_card(channel_id) |

### API 라우트

| 파일 | 역할 |
|---|---|
| `src/api/routes/bot.py` | POST /api/messages — Bot Framework JWT 인증 + 디스패치 |

### Teams 앱 매니페스트

| 파일 | 역할 |
|---|---|
| `teams-app/manifest/manifest.json` | 매니페스트 v1.17, 4개 한국어 명령어, validDomains 플레이스홀더 |
| `teams-app/manifest/color.png.txt` | 192×192 PNG 아이콘 자리 표시자 안내 |
| `teams-app/manifest/outline.png.txt` | 32×32 PNG 아이콘 자리 표시자 안내 |

---

## 3. 핵심 설계 결정 반영

### 신원 확인 (ADR-SEC-006 준수)
모든 핸들러에서 사용자 신원은 `activity.from_.aad_object_id`에서만 읽는다.
카드 payload 또는 submitted_data의 `submitter_aad_id` 필드는 표시 목적으로만
사용하고, 보안 결정에는 절대 사용하지 않는다.

### Task Module 숨김 필드
`task/fetch` 시점에 서버가 바인딩하는 4개 숨김 필드:

```
channel_id       — 채널 컨텍스트
submitter_aad_id — 제출자 AAD ID (표시용; 보안 결정에 미사용)
report_week      — ISO 주차 (예: 2026-W23)
is_late          — 마감 경과 여부 (bool)
```

### 카드 업데이트-인-플레이스
`ChannelConfig`에 저장된 `activity_id`를 사용해 팀장 상태 카드를 제자리 업데이트한다.
`404` 응답 수신 시 `send_card()`로 폴백하고 새 `activity_id`를 저장한다.

### 채널 전용 알림 (DM 없음)
`post_reminder_card()` 및 `post_deadline_card()` 모두 `CardSender.proactive_send()`를
통해 팀 채널에 메시지를 발송한다. 개인 DM은 사용하지 않는다.
@멘션은 카드의 `msteams.entities` 배열로 구현한다.

### 대리 제출 금지 (ADR-006 준수)
팀장이 미제출자를 대리 제출하는 경로가 존재하지 않는다.
마감 후 미제출자는 `is_late=True` 상태로 본인이 직접 제출한다.

### ACL 이중 게이트 — 팀장 등록 (ADR-008, ADR-SEC-002)
1. `INITIAL_ADMIN_AAD_IDS` 환경변수에 등록된 사용자는 언제든 등록 가능
2. 채널에 팀장이 없을 때는 자기 등록 허용
3. 기존 팀장 본인만 재등록 가능

### 스케줄 알림 시각
| 시각 (KST) | 함수 | 내용 |
|---|---|---|
| 목 10:00 | `post_reminder_card()` | 미제출자 @멘션 + 제출 버튼 |
| 목 13:00 | `post_deadline_card()` | 마감 도달, 전원 제출 시 자동 취합 트리거 |

---

## 4. 서비스 계층 의존성

아래 서비스는 Phase 2 병행 구현 대상이다. 현재 `try/except ImportError` 스텁으로
처리되어 있어 Teams 레이어 단독 개발·테스트가 가능하다.

| 서비스 | 경로 (예정) | 용도 |
|---|---|---|
| ReportService | `src/services/reports/report_service.py` | 보고서 저장, 미제출자 조회, ACL |
| ChannelConfigService | `src/services/reports/channel_config_service.py` | 팀장, 지정 보고자, activity_id, ConversationRef 저장 |
| DeadlineService | `src/services/reports/deadline_service.py` | 목 13:00 마감 경과 여부 |
| TeamMemberService | `src/services/reports/team_member_service.py` | Graph API 채널 멤버 조회 |
| AggregationService | `src/services/llm/aggregation_service.py` | LLM 취합 |
| MailService | `src/services/mail/mail_service.py` | Graph 메일 발송 |

---

## 5. Teams 앱 패키징 절차

1. `teams-app/manifest/manifest.json`의 플레이스홀더 치환:
   - `${TEAMS_APP_ID}` → 고유 GUID
   - `${MICROSOFT_APP_ID}` → Bot AAD 앱 등록 ID
   - `${BOT_DOMAIN}` → 봇 호스팅 도메인 (예: `weeklybot.example.com`)
2. 실제 `color.png` (192×192) 및 `outline.png` (32×32) 파일을 동일 폴더에 배치
3. 세 파일을 ZIP으로 묶어 `.zip` 생성
4. Teams 관리 센터 또는 Developer Portal에서 업로드

---

## 6. 다음 단계 (Phase 3)

- 서비스 계층(`ReportService`, `ChannelConfigService` 등) 구현
- DB 스키마 연동
- 스케줄러(`infra/scheduler`) — APScheduler 또는 Azure Functions Timer로 목 10:00·13:00 트리거
- 단위 테스트: 핸들러 ACL, Task Module 폼 빌더, card builder, notification_jobs
- 통합 테스트: Bot Framework Emulator 또는 ngrok 로컬 터널
