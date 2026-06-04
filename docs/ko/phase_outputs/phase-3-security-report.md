# Phase 3 보안 리뷰 보고서

**작성일:** 2026-06-04
**작성자:** @security-reviewer
**검토 대상:** Phase 2 구현 (commit 5654, 2026-06-04)
**검토 기준:** ADR-SEC-001 ~ ADR-SEC-007

---

## 1. ADR-SEC 준수 현황 (Compliance Matrix)

| ADR | 제목 | 상태 | 비고 |
|---|---|---|---|
| ADR-SEC-001 | Delegated OAuth — 앱 권한 없음 | **PARTIAL** | Graph 범위 과다 선언 (이슈 #1) |
| ADR-SEC-002 | 팀장 등록 이중 게이트: INITIAL_ADMIN or 자가 등록 | **PARTIAL** | env 변수 이름 불일치 + 감사 로그 누락 (이슈 #2, #3) |
| ADR-SEC-003 | 삼중 게이트 메일 전송 (gate_check) | **COMPLIANT** | 세 조건 모두 서버 DB 재검증 |
| ADR-SEC-004 | 리프레시 토큰 원자적 쓰기 | **COMPLIANT** | refresh → access → metadata 순서 준수 |
| ADR-SEC-005 | 채널 격리: activity에서만 channel_id 추출, 불일치 거부+로그 | **NON-COMPLIANT** | ActivityValidator 미들웨어 미구현 (이슈 #4) |
| ADR-SEC-006 | 프록시 제출 금지: actor == owner 하드코딩 | **COMPLIANT** | `actor_aad_id != target_aad_id` 즉시 예외 |
| ADR-SEC-007 | Bot JWT 검증: 필수 pre-route 미들웨어 | **PARTIAL** | BotFrameworkHttpAdapter 사용은 맞으나 빈 APP_ID 묵인 (이슈 #5) |

**요약:** 7개 ADR 중 3개 완전 준수, 3개 부분 준수, 1개 미준수.

---

## 2. 발견된 보안 이슈

### 이슈 #1 — [CONFIRMED] Graph 범위 과다 선언 (ADR-SEC-001 위반)

**파일:** `src/services/mail/token_manager.py` 라인 186–190
**파일:** `src/api/routes/auth.py` 라인 92–94

`token_manager.py`의 `refresh_token()` 메서드와 `auth.py`의 `_SCOPES` 상수가 동일하게 다음 범위를 요청한다.

```
openid profile email offline_access User.Read Mail.ReadWrite Mail.Send
```

ADR-SEC-001은 Delegated OAuth만 허용하며 최소 권한을 명시한다. `Mail.ReadWrite`는 초안 생성 및 수정에 필요하지만, 이 프로젝트의 서비스 계층(`graph_client.py`)이 실제로 사용하는 Graph 엔드포인트는 다음과 같다.

- `POST /users/{oid}/messages` — 초안 생성 (Mail.ReadWrite)
- `PATCH /users/{oid}/messages/{id}` — 초안 수정 (Mail.ReadWrite)
- `POST /users/{oid}/messages/{id}/send` — 전송 (Mail.Send)
- `DELETE /users/{oid}/messages/{id}` — 초안 삭제 (Mail.ReadWrite)
- `GET /teams/{id}/channels/{id}/members` — 채널 멤버 조회 (ChannelMember.Read.All)

`User.Read`는 `/me` 폴백(auth.py 라인 240–246)에서만 사용되며, `ChannelMember.Read.All`은 범위 목록에 누락되어 있다. `Mail.ReadWrite`를 선언하면서 동시에 사용하는 것은 최소 권한 원칙 위반은 아니나, `User.Read`는 OID 추출 이후에는 불필요하며 나중에 범위 확장을 은폐하는 위험이 있다.

**심각도:** 낮음 (기능상 범위는 필요하나 `User.Read` 지속 보유는 최소 권한 위반)

---

### 이슈 #2 — [CONFIRMED] env 변수 이름 불일치로 인한 이중 게이트 고장 (ADR-SEC-002 위반)

**파일 A:** `src/adapters/teams/handlers/register_team_lead.py` 라인 112
**파일 B:** `src/infra/config.py` 라인 53–54

`register_team_lead.py`의 `_is_initial_admin()` 함수는 `os.environ.get("INITIAL_ADMIN_AAD_IDS", "")` 를 직접 읽는다.

`config.py`(Settings 모델)는 동일한 개념을 `alias="INITIAL_ADMIN_USER_IDS"`로 선언한다.

`team_lead_service.py`(라인 47)는 `self._settings.initial_admin_user_ids`를 통해 Settings 객체에서 읽는다.

결과: `register_team_lead.py` 핸들러는 `INITIAL_ADMIN_AAD_IDS`를 읽고, `team_lead_service.py`는 `INITIAL_ADMIN_USER_IDS`를 읽는다. 운영자가 `INITIAL_ADMIN_USER_IDS`만 설정하면 핸들러 계층의 Gate 1은 항상 `False`를 반환한다. 신규 채널에서는 Gate 2a("채널에 팀장 없음 → 자가 등록 허용")가 적용되어 **임의 사용자가 팀장으로 등록될 수 있다.**

또한 `team_lead_service.py`의 `register()` 메서드(라인 112)는 `is_first_setup = (existing is None or not existing.is_active)` 조건을 신규 채널 자가 등록 허용 조건으로 사용한다. 이는 ADR-SEC-002 §2("신규 채널: INITIAL_ADMIN_USER_IDS 또는 첫 사용자")와 일치하지만, 핸들러와 서비스의 env 변수 이름이 달라 Gate 1이 핸들러에서 항상 통과되지 않는 버그가 있다.

**심각도:** 높음 — 신규 채널에서 권한 없는 사용자가 팀장 등록 가능

---

### 이슈 #3 — [CONFIRMED] 팀장 등록 실패 시 감사 로그 없음 (ADR-SEC-002 위반)

**파일:** `src/adapters/teams/handlers/register_team_lead.py` 라인 53–54
**파일:** `src/services/acl/team_lead_service.py` 라인 112–118

ADR-SEC-002 "감시 로그" 섹션은 다음 action을 기록하도록 요구한다.

- `unauthorized_team_lead_registration`
- `unauthorized_team_lead_transfer`

`register_team_lead.py`에서 ACL 실패 시(라인 53–54) `_reply()`로 사용자에게 거부 메시지를 보내지만 audit log를 기록하지 않는다. `team_lead_service.py`의 `TeamLeadRegistrationError`를 발생시키는 경로(라인 114–118)도 동일하게 감사 로그가 없다.

**심각도:** 중간 — 보안 사고 탐지 능력 저하, 무단 등록 시도 은폐 가능

---

### 이슈 #4 — [CONFIRMED] 채널 격리 ActivityValidator 미구현 (ADR-SEC-005 위반)

**파일:** `src/services/reports/submission_service.py` (전체)
**파일:** `src/adapters/teams/handlers/register_team_lead.py` (전체)
**파일:** `src/api/dependencies.py` (전체)

ADR-SEC-005는 다음을 요구한다.

1. `channel_id`는 `Activity.channelData.teamsChannelId`에서만 추출 (payload 불신)
2. `activity_channel_id != request_channel_id` 불일치 시 즉시 거부 + 감사 로그

`submission_service.py`는 `channel_id`를 호출자가 전달하는 매개변수로 받는다(라인 47). `register_team_lead.py`의 `_get_channel_id()`(라인 152–157)는 `activity.conversation.id`에서 추출하므로 핸들러 자체는 올바르지만, 서비스 계층에 들어오는 `channel_id`와 activity context의 `channel_id`가 일치하는지 **서비스 계층에서 재검증하지 않는다.**

`dependencies.py`의 `inject_channel_config`는 query parameter에서 `channel_id`를 받으며(라인 26), 이는 HTTP 요청 payload에서 오는 값으로 activity-derived 값과의 불일치 여부를 검사하지 않는다.

크로스 채널 시도 탐지를 위한 `ActivityValidator` 미들웨어가 어떤 파일에도 구현되어 있지 않다.

**심각도:** 높음 — 크로스 채널 데이터 접근 시도를 탐지하거나 차단하는 계층 부재

---

### 이슈 #5 — [CONFIRMED] 빈 APP_ID로 Bot JWT 검증 우회 가능 (ADR-SEC-007 부분 위반)

**파일:** `src/api/routes/bot.py` 라인 44–51

```python
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

_adapter_settings = BotFrameworkAdapterSettings(
    app_id=_APP_ID,
    app_password=_APP_PASSWORD,
)
```

`os.environ.get(..., "")` 는 env 변수가 누락될 때 빈 문자열을 사용한다. Bot Framework SDK는 `app_id`가 빈 문자열이면 **인증 검사를 건너뛰고** 모든 incoming activity를 허용한다 (로컬 에뮬레이터 모드). 프로덕션 환경에서 이 변수가 실수로 누락되면 JWT 검증이 완전히 비활성화된다.

ADR-SEC-007은 "Bot JWT verification은 필수 pre-route 미들웨어"를 요구하며, 조건부 활성화는 허용하지 않는다.

**심각도:** 높음 — 프로덕션에서 env 변수 누락 시 인증 우회 가능

---

### 이슈 #6 — [CONFIRMED] 스케줄러 타임스탬프 재전송 공격 방어 없음 (ADR-SEC-004 인접)

**파일:** `src/api/dependencies.py` 라인 83–112
**파일:** `src/api/routes/scheduler.py` 라인 57–65

`verify_hmac_signature()`는 `{timestamp}:{body}` 를 HMAC 메시지로 사용하지만 `timestamp`의 신선도(freshness)를 검증하지 않는다. 공격자가 유효한 HMAC 요청을 캡처하여 나중에 재전송하면 동일한 검증을 통과한다.

**심각도:** 중간 — 내부 네트워크 정책으로 완화 가능하나 타임스탬프 수락 창 검증이 부재

---

### 이슈 #7 — [SUSPECTED] auth.py의 in-process 상태 저장소 경쟁 조건

**파일:** `src/api/routes/auth.py` 라인 47–52

`_pending_states` 딕셔너리가 모듈 레벨 전역 변수다. 다중 워커 프로세스 환경(Gunicorn 등)에서는 프로세스 간 공유되지 않아 CSRF state 검증이 실패할 수 있다. 코드 주석(라인 44–46)에 "For production consider a Redis-backed store"라고 명시되어 있어 개발자가 인지하고 있으나 Phase 2에서 수정되지 않았다.

**심각도:** 중간 (단일 프로세스 배포 시 무해, 다중 워커 시 PKCE 흐름 파손)

---

## 3. 수정 권고사항

### Fix #1 — 이슈 #2: env 변수 이름 통일

`src/adapters/teams/handlers/register_team_lead.py` 라인 112의 `_is_initial_admin()` 함수가 직접 `os.environ`을 읽지 말고 `get_settings().initial_admin_user_ids`를 사용해야 한다. 또는 env 변수 이름을 `INITIAL_ADMIN_AAD_IDS`로 통일하고 `config.py`의 alias를 수정해야 한다. 자세한 코드는 `phase-3-security-patches.md` Fix-A 참조.

### Fix #2 — 이슈 #3: 감사 로그 추가

`register_team_lead.py`의 ACL 거부 분기와 `team_lead_service.py`의 `TeamLeadRegistrationError` 발생 지점에 audit log 기록을 추가한다. `phase-3-security-patches.md` Fix-B 참조.

### Fix #3 — 이슈 #4: ActivityValidator 미들웨어 구현

Bot 핸들러에서 `channel_id`를 서비스 계층에 전달하기 전에 `activity.channelData.teamsChannelId`와 일치하는지 검증하는 헬퍼를 구현한다. 불일치 시 예외를 발생시키고 audit log를 기록한다. `phase-3-security-patches.md` Fix-C 참조.

### Fix #4 — 이슈 #5: APP_ID 빈 문자열 거부

`bot.py`에서 `MICROSOFT_APP_ID` 또는 `MICROSOFT_APP_PASSWORD`가 비어 있으면 시작 시 `RuntimeError`를 발생시킨다. `phase-3-security-patches.md` Fix-D 참조.

### Fix #5 — 이슈 #6: HMAC 타임스탬프 신선도 검증

`verify_hmac_signature()` 또는 호출자에서 `|timestamp - now| > 300초` 이면 401을 반환한다. `phase-3-security-patches.md` Fix-E 참조.

### Fix #6 — 이슈 #7: Redis 기반 state 저장소 (Phase 4 권고)

`_pending_states`를 Redis TTL 키로 교체한다. 단일 워커 배포라면 즉각 위험은 없으나 Phase 4 배포 전에 수정한다.

---

## 4. Phase 2 보안 체크리스트 결과

| 항목 | 결과 |
|---|---|
| Delegated OAuth만 사용 (앱 권한 없음) | PASS (graph_client.py 위임 전용) |
| Graph 범위 최소화 | FAIL (User.Read 잉여) |
| 팀장 등록: activity에서만 identity 추출 | PASS (register_team_lead.py) |
| 팀장 등록: INITIAL_ADMIN 또는 자가 등록 게이트 | FAIL (env 변수 이름 불일치) |
| 팀장 등록 실패 감사 로그 | FAIL (미구현) |
| 삼중 게이트 메일 전송 (server-side DB 재검증) | PASS |
| 메일 자동 전송 없음 (팀장 승인 후 전송) | PASS |
| 리프레시 토큰 원자적 쓰기 | PASS |
| channel_id activity-only 추출 + 불일치 거부 | FAIL (ActivityValidator 미구현) |
| 프록시 제출 금지 (actor == owner) | PASS |
| Bot JWT 검증 필수 활성화 | FAIL (빈 APP_ID 묵인) |
| 스케줄러 HMAC 검증 | PASS (HMAC 구현됨, 신선도만 누락) |
| 토큰 값 로그 미기록 | PASS |
| 클라이언트에 토큰 값 미반환 | PASS |

**결과 요약:** 14개 항목 중 9개 통과, 5개 실패.
