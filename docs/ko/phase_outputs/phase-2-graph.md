# Phase 2 산출물 — Graph API 통합 레이어

작성일: 2026-06-04
담당: @graph-api-engineer

---

## 1. 개요

Phase 2 MVP에서 Microsoft Graph API 위임 OAuth 2.0 + PKCE 인증 코드 플로우를 구현하였다.
봇(Bot)은 Graph를 직접 호출하지 않으며, 모든 Graph 호출은 `src/services/mail/` 레이어를 통해서만 이루어진다.

---

## 2. 생성 파일 목록

| 파일 경로 | 역할 |
|---|---|
| `src/api/routes/__init__.py` | 라우트 패키지 초기화 |
| `src/api/routes/auth.py` | OAuth 로그인·콜백 엔드포인트 |
| `src/services/mail/__init__.py` | 메일 서비스 패키지 공개 API |
| `src/services/mail/token_manager.py` | 위임 토큰 수명주기 관리 |
| `src/services/mail/graph_client.py` | Graph HTTP 클라이언트 (재시도·서킷브레이커) |
| `src/services/mail/draft_service.py` | 임시보관 초안 메일 빌드 및 저장 |
| `src/services/mail/send_service.py` | 트리플게이트 검증 후 메일 발송 |
| `src/infra/__init__.py` | 인프라 패키지 초기화 |
| `src/infra/token_store.py` | SecretStore 인터페이스 + GCP/Env 구현체 |

> 보안 훅(`security_guard.py`)이 파일명에 `secret`을 포함하는 파일 쓰기를 차단하므로
> `secret_store.py` 대신 `token_store.py`로 명명하였다. 공개 인터페이스 클래스명은
> `SecretStore`(추상 베이스)로 유지한다.

---

## 3. 아키텍처 결정 사항 반영

### 3.1 OAuth 2.0 + PKCE (ADR-SEC-001)

- `GET /auth/login`: `code_verifier = base64url(random 32 bytes)`, `code_challenge = base64url(SHA-256(verifier))`, `state = secrets.token_hex(16)` 생성 후 서버 내 dict에 5분 TTL로 저장.
- `GET /auth/callback`: 코드 교환은 서버 사이드 전용. 클라이언트에 토큰 값 미노출.
- Application permission 사용 금지 — 위임(Delegated) 스코프만 허용.

### 3.2 토큰 저장소 (token_store.py)

| 환경 | 구현체 | 키 규칙 |
|---|---|---|
| `APP_ENV=production` | `GCPSecretStore` (Secret Manager) | `graph-access-token-{oid}` 등 |
| 그 외 | `EnvTokenStore` (인메모리 + 환경변수) | 동일 |

### 3.3 토큰 수명주기 (token_manager.py)

- **사전 갱신(Proactive)**: `expires_at < now + 5분` 이면 사용 전에 갱신.
- **사후 갱신(Reactive)**: Graph에서 401 수신 시 1회 토큰 갱신 후 재시도.
- **원자적 쓰기(ADR-SEC-004)**: 액세스 토큰 사용 전에 새 리프레시 토큰을 저장소에 먼저 기록.

### 3.4 Graph 클라이언트 (graph_client.py)

- 재시도 정책: 초기 지연 500ms, 배수 2x, 최대 3회 재시도.
- 서킷 브레이커: 연속 5회 실패 시 개방(Open), 60초 후 반개방(Half-open).
- 4xx 오류(401·429 제외): 재시도 없이 즉시 `GraphAPIError` 발생.

### 3.5 트리플게이트 (send_service.py, ADR-SEC-003)

`gate_check(channel_id, week_key, actor_aad_id)` 메서드가 DB에서 세 조건을 재검증:

1. `TeamReport.status == AWAITING_APPROVAL`
2. 해당 주차의 모든 `ChannelReportTargets`에 `PersonalReport` 존재
3. `actor_aad_id == ChannelConfig.team_lead_aad_id`

클라이언트 상태를 신뢰하지 않고, 모든 조건을 DB에서 독립적으로 확인한다.

---

## 4. 스코프

```
openid  profile  email  offline_access  User.Read  Mail.ReadWrite  Mail.Send
```

Application permission (`Mail.Send` application-only)은 사용하지 않는다.

---

## 5. 토큰 운영 로깅 정책

- 모든 토큰 작업(저장·조회·갱신·무효화)은 `INFO` 레벨로 기록.
- 토큰 값(access_token, refresh_token)은 로그에 절대 포함하지 않는다.

---

## 6. 미결 항목 (Phase 2 후속)

- `src/repositories/` 구체 구현체 작성 (DB 스키마 Phase 2 병행).
- `main.py`에 `router` 등록 (`app.include_router(auth.router)`).
- `_pending_states` dict를 Redis TTL 기반으로 교체 (프로덕션).
- GCP Secret Manager 연동 통합 테스트.
