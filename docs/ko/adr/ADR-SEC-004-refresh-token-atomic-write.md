---
id: ADR-SEC-004
title: Refresh Token 원자성: Secret Manager 우선 쓰기
status: Accepted
date: 2026-06-04
---

# ADR-SEC-004: Refresh Token 원자성: Secret Manager 우선 쓰기

## 상태
확정 (Accepted)

## 맥락

OAuth refresh flow:

1. **요청:** 팀장이 Graph API 호출
2. **확인:** access token이 만료되었나?
3. **갱신:** refresh token으로 새 access + refresh token 획득
4. **저장:** GCP Secret Manager에 저장
5. **사용:** 새 access token으로 API 호출

**문제:** 단계 4와 5 사이에 실패하면 어떻게 되는가?

옵션 1: 새 token을 메모리에만 저장 후 사용 (실패 시 재인증)
옵션 2: 새 token을 먼저 저장 후 사용 (저장 실패 시 operation abort)
옵션 3: 새 token을 먼저 사용 후 저장 (사용 실패 시 저장 안 함)

## 결정

**새 refresh token을 Secret Manager에 먼저 쓴 후 access token으로 API를 호출한다. Secret Manager 쓰기 실패 시 operation을 abort한다.**

```python
async def ensure_valid_token(team_lead_aad_id: str) -> str:
    """
    Get valid access token, refreshing if needed.
    Atomic write: new token → Secret Manager FIRST.
    """
    # 1. Get current token from Secret Manager
    current_token = await secret_manager.get(
        f"graph-access-token-{team_lead_aad_id}"
    )

    # 2. Check if expired
    if not is_expired(current_token):
        return current_token.access_token

    # 3. Refresh using refresh token
    refresh_token = await secret_manager.get(
        f"graph-refresh-token-{team_lead_aad_id}"
    )

    new_tokens = await graph_client.refresh_access_token(
        refresh_token.value
    )

    # 4. CRITICAL: Write to Secret Manager FIRST
    try:
        await secret_manager.put(
            f"graph-refresh-token-{team_lead_aad_id}",
            new_tokens.refresh_token,
            metadata={"expires_at": new_tokens.refresh_expires_at}
        )
        await secret_manager.put(
            f"graph-access-token-{team_lead_aad_id}",
            new_tokens.access_token,
            metadata={"expires_at": new_tokens.access_expires_at}
        )
    except Exception as e:
        # Secret Manager write failed
        # DO NOT use new token
        await audit_log_repo.log(
            action="token_refresh_failed",
            reason="secret_manager_write_failed",
            actor_aad_id=team_lead_aad_id,
            details={"error": str(e)}
        )
        raise RefreshTokenError(
            "Failed to save new token. Re-authentication required."
        )

    # 5. THEN use new access token
    return new_tokens.access_token
```

## 근거

### 1. Prevent Stale Token Reuse
- 옵션 3 (먼저 사용)은 위험:
  - API 호출 성공 → Secret Manager 저장 실패
  - 다음 갱신 때 옛날 token으로 재시도 (expired)

### 2. Ensure Exactly-One Version
- Secret Manager에 저장된 token = "현재 유효한" token
- 애플리케이션 메모리와 Secret Manager 불일치 방지
- Distributed system에서 single source of truth

### 3. Fail-Safe Design
- Secret Manager 쓰기 실패 → operation abort
- 사용자는 재인증 필요 (명확한 오류)
- 조용한 실패(silent failure) 방지

### 4. Race Condition 방지
- 여러 요청이 동시에 갱신 시도
- Atomic write로 마지막 저장된 token이 "current"
- Compare-and-swap 또는 versioning으로 추가 보호 가능

## 결과

### 긍정
- **안정성:** token version 불일치 불가능
- **감시:** 저장 실패는 즉시 감지
- **명확성:** 사용자는 명시적으로 재인증

### 부작용
- **성능:** Secret Manager write latency (보통 100ms 이상)
- **복잡도:** 에러 핸들링 복잡함

### 제약
- **Distributed Transactions:** Secret Manager write와 API call이 atomic이 아님
  → Idempotency key 필요 (멱등성)

## 구현 세부사항

### Idempotency

```python
# API 호출이 실패해도 token은 이미 저장됨
# → 재시도는 새 token으로 자동 진행
async def send_mail_with_retry(
    team_lead_aad_id: str,
    draft_id: str,
    idempotency_key: str  # unique per request
):
    access_token = await ensure_valid_token(team_lead_aad_id)

    # Graph API는 idempotency_key를 지원할 수 있음
    response = await graph_client.send_mail(
        access_token,
        draft_id,
        headers={"Idempotency-Key": idempotency_key}
    )
```

### Compare-and-Swap

```python
# Secret Manager versioning으로 race condition 방지
async def save_token_with_version(
    team_lead_aad_id: str,
    new_token: str,
    expected_old_version: int
):
    try:
        await secret_manager.update_with_version(
            f"graph-refresh-token-{team_lead_aad_id}",
            new_token,
            expected_version=expected_old_version
        )
    except VersionMismatchError:
        # Another request already updated → abort
        raise RefreshTokenError("Token was concurrently updated")
```

## 감시 로그

- action: "token_refresh_succeeded"
- actor_aad_id: team lead
- timestamp: refresh 시각

- action: "token_refresh_failed"
- reason: "secret_manager_write_failed" or "graph_refresh_failed"
- actor_aad_id: team lead

## 참고

- ADR-004: Scheduler Auth (secret 관리)
- [Secret Manager Best Practices](https://cloud.google.com/secret-manager/docs/best-practices)
