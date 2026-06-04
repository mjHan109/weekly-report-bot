---
id: ADR-SEC-002
title: Team Lead Registration ACL: INITIAL_ADMIN_USER_IDS + Self-Register Validation
status: Accepted
date: 2026-06-04
---

# ADR-SEC-002: Team Lead Registration ACL: INITIAL_ADMIN_USER_IDS + Self-Register Validation

## Status
Accepted

## Context

Team lead registration is the first authorization step. Who can become team lead?

Security concerns:
- Unauthorized users must not register as team lead
- Is bot framework activity trustworthy?

## Decision

**Team lead registration ACL uses dual-gate:**

1. **Identity Source:** trust only Activity.from.aadObjectId (ignore card payload)
2. **Authorization:**
   - New channel: INITIAL_ADMIN_USER_IDS or first user
   - Existing channel: current lead only for transfer
3. **Failure on Missing Env:** startup fails if INITIAL_ADMIN_USER_IDS missing

## Rationale

### 1. Bot Framework Activity is Trusted Source
- Microsoft-verified JWT token
- aadObjectId verified by Azure AD
- Cannot be forged (signed with private key)

### 2. Payload is Untrusted
```json
// malicious payload (forged)
{
  "channel_id": "hacked-channel",
  "team_lead_aad_id": "attacker-aad-id"
}
```

- Client can fabricate arbitrary payload
- Activity context cannot be overridden

### 3. INITIAL_ADMIN_USER_IDS Enforcement
- Missing env var causes startup failure
- Misconfiguration detected immediately
- Operator must set intentionally

### 4. First Team Lead Assignment Reliability
- Only INITIAL_ADMIN_USER_IDS users can register first
- Trusted organizational personnel (admins, etc.)

## Consequences

### Positive
- **Security:** unauthorized team lead registration impossible
- **Audit:** missing bootstrap detected immediately
- **Transparency:** initial team leads explicit in INITIAL_ADMIN_USER_IDS

### Drawbacks
- **Operations:** env var management required
- **Onboarding:** set environment before first team lead registers

## Implementation

```python
# startup hook
def check_bootstrap():
    initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS")
    if not initial_admins:
        raise RuntimeError(
            "INITIAL_ADMIN_USER_IDS not set. "
            "Cannot bootstrap system without initial admins."
        )

# register endpoint
async def register_team_lead(
    channel_id: str,
    activity: Activity  # Bot Framework Activity (trusted)
):
    # Extract ID from Activity only
    requester_aad_id = activity.from.aadObjectId

    channel = await channel_repo.find_by_channel_id(channel_id)

    if not channel:
        # New channel: validate INITIAL_ADMIN_USER_IDS
        initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS").split(",")
        if requester_aad_id not in initial_admins:
            await audit_log_repo.log(
                channel_id=channel_id,
                action="unauthorized_team_lead_registration",
                actor_aad_id=requester_aad_id
            )
            raise PermissionDenied("Not authorized to register")

    else:
        # Existing channel: current lead only
        if requester_aad_id != channel.team_lead_aad_id:
            await audit_log_repo.log(
                channel_id=channel_id,
                action="unauthorized_team_lead_transfer",
                actor_aad_id=requester_aad_id,
                details={"current_lead": channel.team_lead_aad_id}
            )
            raise PermissionDenied("Not current team lead")

    # register/transfer
    ...
```

## Audit Logging

- action: "unauthorized_team_lead_registration"
- actor_aad_id: unauthorized attempt actor
- details: { "channel_id", "timestamp" }

## References

- ADR-008: team lead registration (technical perspective)
- Bot Framework JWT verification (reliability)
