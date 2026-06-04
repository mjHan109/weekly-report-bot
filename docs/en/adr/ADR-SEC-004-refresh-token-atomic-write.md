---
id: ADR-SEC-004
title: Refresh Token Atomicity: Secret Manager Flush First
status: Accepted
date: 2026-06-04
---

# ADR-SEC-004: Refresh Token Atomicity: Secret Manager Flush First

## Status
Accepted

## Context

OAuth refresh flow:

1. **Request:** team lead calls Graph API
2. **Check:** access token expired?
3. **Refresh:** use refresh token → get new access + refresh token
4. **Save:** write to GCP Secret Manager
5. **Use:** call Graph API with new access token

**Question:** if failure between steps 4 and 5?

Option 1: save new token to memory only, use it (retry on failure)
Option 2: save to Secret Manager first, then use (abort on save failure)
Option 3: use first, then save (don't save on use failure)

## Decision

**Write new refresh token to Secret Manager FIRST, then use new access token for API call. If Secret Manager write fails, abort operation.**

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

## Rationale

### 1. Prevent Stale Token Reuse
- Option 3 (use first) is risky:
  - API succeeds → Secret Manager save fails
  - Next refresh retries with old token (expired)

### 2. Ensure Exactly-One Version
- Token in Secret Manager = "currently valid" token
- Prevents app memory and Secret Manager desync
- Distributed system single source of truth

### 3. Fail-Safe Design
- Secret Manager write failure → abort operation
- User explicitly re-authenticates (clear error)
- No silent failures

### 4. Prevent Race Conditions
- Multiple requests attempt refresh concurrently
- Atomic write ensures last-saved token is "current"
- Compare-and-swap or versioning for extra protection

## Consequences

### Positive
- **Stability:** token version mismatch impossible
- **Audit:** save failure detected immediately
- **Clarity:** user explicitly re-authenticates

### Drawbacks
- **Performance:** Secret Manager write latency (100ms+)
- **Complexity:** error handling intricate

### Constraints
- **Distributed Transactions:** Secret Manager write and API call not atomic
  → Idempotency key needed

## Implementation Details

### Idempotency

```python
# API call fails, but token already saved
# → retry automatically uses new token
async def send_mail_with_retry(
    team_lead_aad_id: str,
    draft_id: str,
    idempotency_key: str  # unique per request
):
    access_token = await ensure_valid_token(team_lead_aad_id)

    # Graph API can support idempotency_key
    response = await graph_client.send_mail(
        access_token,
        draft_id,
        headers={"Idempotency-Key": idempotency_key}
    )
```

### Compare-and-Swap

```python
# Secret Manager versioning prevents race conditions
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

## Audit Logging

- action: "token_refresh_succeeded"
- actor_aad_id: team lead
- timestamp: refresh time

- action: "token_refresh_failed"
- reason: "secret_manager_write_failed" or "graph_refresh_failed"
- actor_aad_id: team lead

## References

- ADR-004: Scheduler Auth (secret management)
- [Secret Manager Best Practices](https://cloud.google.com/secret-manager/docs/best-practices)
