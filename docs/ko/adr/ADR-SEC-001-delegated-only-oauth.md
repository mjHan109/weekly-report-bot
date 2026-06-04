---
id: ADR-SEC-001
title: OAuth 범위: Delegated-Only (Application Permissions 금지)
status: Accepted
date: 2026-06-04
---

# ADR-SEC-001: OAuth 범위: Delegated-Only (Application Permissions 금지)

## 상태
확정 (Accepted)

## 맥락

Microsoft Graph API는 두 가지 권한 모델을 제공한다:

1. **Delegated Permissions:** 로그인한 사용자의 맥락에서 동작
   - 사용자 consent 필요
   - 사용자의 리소스만 접근 가능
   - 예: "Mail.Send"로 사용자의 메일함만 접근

2. **Application Permissions:** 봇의 고유 ID로 동작 (app-only)
   - 사용자 consent 불필요
   - 모든 사용자/리소스 접근 가능
   - 예: "Mail.Send"로 모든 사용자의 메일 발송 가능

**문제:** 어떤 권한을 사용할 것인가?

## 결정

**오직 Delegated Permissions만 사용한다. Application Permissions는 영구적으로 금지한다.**

코드 리뷰 gate:
- CI lint rule: msgraph API 호출에서 non-delegated scope 탐지 → fail
- 이 결정을 ADR로 명시하여 exception 불가능

## 근거

### 1. 보안: 접근 범위 최소화
- Application permissions는 봇이 모든 사용자의 메일을 읽고 쓸 수 있음
- Delegated는 "팀장이 동의한 메일함만" 접근 가능
- 침해(breach) 시 blast radius 극도로 축소

### 2. 규정 준수 (Compliance)
- GDPR, HIPAA 등 규정: "최소 권한 원칙"
- Application permissions는 과도한 권한
- Delegated는 명확한 동의 경로

### 3. 감시 (Audit Trail)
- Delegated 사용 시 각 팀장이 누가 언제 consent했는지 추적 가능
- Application permissions는 추적 어려움 (봇 고유 ID로만 기록)

### 4. 신뢰성 (Trust)
- 조직에서 "봇이 무한정 권한을 가질 수 없다"는 정책 신뢰
- 팀장들이 메일 봇 사용 허용 (explicit consent)

## 결과

### 긍정
- **보안:** 침해 시 한 팀장의 메일만 영향 (전사 메일 아님)
- **규정:** GDPR, HIPAA 준수
- **신뢰:** 조직의 신뢰도 향상

### 부작용
- **복잡도:** 각 팀장이 OAuth consent 필수 (온보딩 단계 추가)
- **관리:** 팀장 변경 시 새로운 consent 필요
- **운영:** token refresh 로직 복잡

### 제약
- **확장성:** "모든 사용자의 메일 수집" 같은 기능 불가능 (새 ADR 필요)

## 구현 체크리스트

### CI/CD Lint Rule

```python
# .github/workflows/security-checks.yml
- name: Check Graph API Permissions
  run: |
    grep -r "AppPassword" src/ && exit 1  # application-only pattern
    grep -r "application/permissions" src/ && exit 1
    exit 0
```

### Delegated Scope 정의

```python
# src/config.py
GRAPH_SCOPES = [
    "Mail.Send",      # delegated only
    "User.Read",      # delegated only
]

NON_APPROVED_SCOPES = [
    "Mail.Read",      # too broad, not needed
    "Mail.ReadWrite", # can modify all mail, too risky
    "Mail.*",         # anything not explicitly approved
]
```

### OAuth Flow (Delegated)

```python
# OAuth 콜백 시 팀장의 동의로 access token 획득
async def oauth_callback(code: str, state: str):
    token = await graph_client.get_token_with_auth_code(
        code,
        GRAPH_SCOPES  # delegated scopes only
    )
    # token은 팀장 context에서만 유효
    await secret_manager.save_token(
        f"graph-access-token-{team_lead_aad_id}",
        token
    )
```

## 감시 및 검증

- [ ] Code review: 모든 graph-sdk 호출 검사 (AppPermission 없음)
- [ ] CI lint: GRAPH_SCOPES 외의 scope 탐지
- [ ] Audit log: 각 팀장의 consent 기록
- [ ] Security scanning: "application/permissions" 문자열 검사

## 예외 처리

**예외는 불가능하다.**

만약 향후 application permissions이 필수라면 새로운 ADR을 작성해야 한다. 이 결정을 override하려면:
1. CTO 승인
2. 보안 팀 감사
3. 새로운 ADR 작성
4. 규정 검토 (GDPR, HIPAA 등)

## 참고

- [Microsoft Graph Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference)
- [Delegated vs Application](https://learn.microsoft.com/en-us/graph/auth-v2-service)
- [GDPR Data Protection](https://gdpr-info.eu/)
