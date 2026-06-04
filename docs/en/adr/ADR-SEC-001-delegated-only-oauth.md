---
id: ADR-SEC-001
title: OAuth Scope: Delegated-Only (Application Permissions Prohibited)
status: Accepted
date: 2026-06-04
---

# ADR-SEC-001: OAuth Scope: Delegated-Only (Application Permissions Prohibited)

## Status
Accepted

## Context

Microsoft Graph API provides two permission models:

1. **Delegated Permissions:** operate in context of signed-in user
   - User consent required
   - User's resources only accessible
   - Example: "Mail.Send" accesses only user's mailbox

2. **Application Permissions:** operate under bot's own identity (app-only)
   - User consent not required
   - All users/resources accessible
   - Example: "Mail.Send" can send from any user's mailbox

**Question:** which permission model?

## Decision

**Use only Delegated Permissions. Application Permissions permanently prohibited.**

Code review gate:
- CI lint rule: detect non-delegated scope in msgraph API calls → fail
- ADR explicitly forbids exceptions

## Rationale

### 1. Security: Minimize Access Scope
- Application permissions allow bot to read/write all users' mail
- Delegated limits to "team leads who consented" mailbox
- On breach, blast radius minimized

### 2. Compliance
- GDPR, HIPAA, etc: "least privilege principle"
- Application permissions excessive
- Delegated has explicit consent path

### 3. Audit Trail
- Delegated: track when each team lead consented
- Application permissions: hard to track (bot identity only)

### 4. Trust
- Organization trusts "bot doesn't have unlimited power"
- Team leads willing to permit mail bot (explicit consent)

## Consequences

### Positive
- **Security:** breach affects single team lead mailbox (not entire org)
- **Compliance:** GDPR, HIPAA adherence
- **Trust:** organizational confidence boosted

### Drawbacks
- **Complexity:** each team lead must OAuth consent (onboarding step)
- **Management:** team lead change requires new consent
- **Operations:** token refresh logic complex

### Constraints
- **Scalability:** "collect all users' mail" impossible (new ADR needed)

## Implementation Checklist

### CI/CD Lint Rule

```python
# .github/workflows/security-checks.yml
- name: Check Graph API Permissions
  run: |
    grep -r "AppPassword" src/ && exit 1  # application-only pattern
    grep -r "application/permissions" src/ && exit 1
    exit 0
```

### Delegated Scope Definition

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
# On OAuth callback, team lead's consent grants access token
async def oauth_callback(code: str, state: str):
    token = await graph_client.get_token_with_auth_code(
        code,
        GRAPH_SCOPES  # delegated scopes only
    )
    # token valid only in team lead context
    await secret_manager.save_token(
        f"graph-access-token-{team_lead_aad_id}",
        token
    )
```

## Monitoring and Validation

- [ ] Code review: inspect all graph-sdk calls (no AppPermission)
- [ ] CI lint: detect scopes outside GRAPH_SCOPES
- [ ] Audit log: track each team lead's consent
- [ ] Security scan: grep for "application/permissions" strings

## Exception Handling

**Exceptions are not possible.**

If application permissions become required in future:
1. Requires CTO approval
2. Security team audit
3. New ADR must be written
4. Compliance review (GDPR, HIPAA, etc.)

## References

- [Microsoft Graph Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference)
- [Delegated vs Application](https://learn.microsoft.com/en-us/graph/auth-v2-service)
- [GDPR Data Protection](https://gdpr-info.eu/)
