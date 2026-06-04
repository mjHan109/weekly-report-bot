# 필요 환경 및 기술 구성

> **문서 동기화 규칙:** 본 문서를 수정할 때는 `docs/en/02_required_environment.md`를 동일한 구조·의미로 함께 수정한다.

## 1. Microsoft 365 환경
- Microsoft Teams 사용 가능 테넌트
- Outlook / Exchange Online 사용 가능 계정
- Microsoft Entra ID 앱 등록 권한
- Teams Developer Portal 접근 권한
- Microsoft 365 Agents Toolkit 또는 Teams 앱 개발 환경

## 2. 권장 개발 방식
Claude Agent Teams를 사용하여 역할별 에이전트가 병렬로 설계, 구현, 리뷰, 테스트를 진행한다.

권장 구현 방식은 **Teams Bot + Backend API + Delegated Microsoft Graph API** 구성이다.

```text
Microsoft Teams (채널별 독립)
→ Teams Bot / Adaptive Card
→ Backend API
→ Report Service / LLM Service
→ Delegated Microsoft Graph API (팀장 OAuth)
→ Outlook Draft / Send
```

## 3. Backend 권장 스택
- Python FastAPI 또는 Node.js Express/NestJS
- PostgreSQL 또는 SQLite
- SQLAlchemy/Prisma 등 ORM
- LLM API 연동 모듈
- Microsoft Graph API Client (Delegated token)
- 환경변수 기반 설정 관리

## 4. GCP 사용 시 권장 구성
- Cloud Run: Backend API 배포
- Cloud SQL: 보고서 및 이력 저장
- Secret Manager: Graph Client Secret, refresh token, LLM API Key 저장
- Cloud Logging: 운영 로그
- Artifact Registry: 컨테이너 이미지 저장
- Cloud Scheduler:
  - **매주 목요일 10:00 KST** — 미제출자 작성 독려 (채널 메시지)
  - **매주 목요일 13:00 KST** — 마감·미제출자·팀장 발송 불가 안내 (채널 메시지)

## 5. 로컬 개발 환경
- VS Code
- Microsoft 365 Agents Toolkit 확장
- Node.js LTS
- Python 3.11 이상
- Docker Desktop
- ngrok 또는 dev tunnel
- Git
- Claude Code / Claude Agent Teams

## 6. Microsoft Graph 인증 (Delegated 확정)
### 6.1 Bot vs Graph 역할 분리
| 구성요소 | 역할 | 인증 방식 |
|---|---|---|
| Teams Bot | 명령어, Adaptive Card, 승인 UI | Bot Framework App ID + Password |
| Backend API | 비즈니스 로직, DB, LLM | 서비스 자체 인증 |
| Graph Mail | Outlook 초안·발송 | **팀장 Delegated OAuth** |

Bot은 Outlook에 직접 접근하지 않는다. 메일 API는 **팀장이 로그인하여 위임한 토큰**으로만 호출한다.

### 6.2 MVP Delegated OAuth 흐름
1. Entra ID에 앱 등록 (Web/API + Bot 등록 연동)
2. 팀장 최초 메일 기능 사용 시 OAuth 로그인 (Authorization Code + PKCE)
3. refresh token을 Secret Manager/DB에 암호화 저장
4. 메일 초안: `POST /me/messages`
5. 팀장 `발송` 승인: `POST /me/sendMail` 또는 draft send

**Application permission(앱 전용)** 으로 사용자 개인 메일함에 접근하는 방식은 MVP에서 사용하지 않는다.

### 6.3 MVP Graph scope (Delegated)
| Scope | 용도 |
|---|---|
| `openid`, `profile`, `email` | 사용자 식별 |
| `offline_access` | refresh token |
| `User.Read` | 프로필 조회 |
| `Mail.ReadWrite` | 메일 초안 생성 |
| `Mail.Send` | 팀장 승인 후 발송 |

관리자 동의(Admin consent) 필요 여부는 테넌트 정책에 따른다. 운영 배포 전 security-reviewer 검토 필수.

## 7. Teams Bot·채널 구성
- **알림:** Bot → **팀 채널 메시지**만 (리마인더 DM 없음)
- manifest.json, color.png, outline.png
- bot id, validDomains
- scopes: `personal`, `team`
- command list (한국어 MVP: `이번 주 보고 작성`, `팀 주간 보고 취합`, `팀장 등록`)
- Adaptive Card templates (미리보기·액션)
- **Task Module** (`task/fetch`) — 주간 보고 입력 폼
- 채널 ID를 모든 보고·설정·취합·발송의 기본 키로 사용

## 8. DB 스키마
- 상세 스키마는 **개발과 병행**하여 정의한다.
- Phase 1: 핵심 엔티티 목록 확정
- Phase 2: 마이그레이션으로 구체화
- 후보 엔티티: `ChannelConfig`, `PersonalReport`, `TeamReport`, `RevisionHistory`, `MailDraft`, `AuditLog`, `ReminderLog`
- `ChannelConfig`: `team_lead_user_id`, `mail_to`, `mail_cc`, `reminder_time`(기본 10:00)
- 환경변수 `INITIAL_ADMIN_USER_IDS`: `팀장 등록` 가능한 최초 관리자 (쉼표 구분 Teams/AAD user ID)

## 9. 운영 설정 파일 예시
```yaml
app:
  env: local
  base_url: https://example.com
  timezone: Asia/Seoul
  reporting_week_start: THU_13:00  # 이전 목 13:00:01 ~ 이번 목 13:00:00
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
  auth_type: delegated  # MVP 확정

llm:
  provider: anthropic
  model: claude-sonnet
  api_key: ${LLM_API_KEY}

database:
  url: ${DATABASE_URL}
```

## 10. 관련 문서
- 확정 결정사항: `docs/ko/05_project_decisions.md`
- Graph·Bot 상세 설명: §6 및 `05_project_decisions.md` §5
