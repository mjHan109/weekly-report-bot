---
id: ADR-008
title: Team Lead Registration Bootstrap: INITIAL_ADMIN_USER_IDS vs Self-Register
status: Accepted
date: 2026-06-04
---

# ADR-008: Team Lead Registration Bootstrap: INITIAL_ADMIN_USER_IDS vs Self-Register

## Status
Accepted

## Context

When a new channel is added, who registers as team lead?

Option 1: admin pre-registers in env var (INITIAL_ADMIN_USER_IDS)
Option 2: anyone can self-register (security risk)
Option 3: team lead can self-register, then transfer only

**Question:** balance security and convenience

## Decision

**Dual-gate approach:**

1. **New Channel (first team lead registration):**
   - Only users in INITIAL_ADMIN_USER_IDS can register
   - Or self-registration allowed (only if channel has no team lead)
   - Missing env var causes startup failure

2. **Existing Channel (team lead transfer):**
   - Current team lead only can transfer role to another
   - New team lead cannot re-register (prevent overwrite)

### Implementation Logic

```python
async def register_team_lead(
    channel_id: str,
    user_aad_id: str,  # from Activity
    activity: Activity
) -> ChannelConfig:
    # Extract user_aad_id from Activity only (ignore payload)
    requester_aad_id = activity.from.aadObjectId

    # Look up channel config
    channel_config = await self.channel_repo.find_by_channel_id(channel_id)

    if not channel_config:
        # New channel: INITIAL_ADMIN_USER_IDS or self-register
        initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS", "").split(",")

        if requester_aad_id not in initial_admins:
            # Self-register (only if channel has no team lead)
            raise PermissionDenied(
                "Not in INITIAL_ADMIN_USER_IDS. "
                "Channel must have at least one initial admin."
            )

        channel_config = ChannelConfig(
            channel_id=channel_id,
            team_lead_aad_id=requester_aad_id,
            team_name="Team"  # default
        )
    else:
        # Existing channel: only current team lead can transfer
        if requester_aad_id != channel_config.team_lead_aad_id:
            raise PermissionDenied(
                "Only current team lead can transfer ownership"
            )

        # Current team lead transfers to another
        channel_config.team_lead_aad_id = user_aad_id

    await self.channel_repo.save(channel_config)
    return channel_config
```

## Rationale

### 1. Security: Prevent Unauthorized Registration
- INITIAL_ADMIN_USER_IDS managed by organization
- Missing env var causes startup failure → detects misconfiguration

### 2. Convenience: Self-Registration
- First team lead can register themselves
- Minimal admin intervention
- Fast onboarding

### 3. Transfer Security: Current Team Lead Only
- Team lead transfers role to another person
- Prevents unauthorized registration (no overwrite)

### 4. Audit: Activity Source Verification
- Ignore payload user_aad_id
- Trust only Activity.from.aadObjectId (Bot Framework verified)

## Consequences

### Positive
- **Security:** prevent unauthorized team lead assignment
- **Audit:** detect bootstrap misconfiguration immediately (startup failure)
- **Flexibility:** first team lead self-registers, then lead controls

### Drawbacks
- **Operations:** env var management required
- **Migration:** channels without team lead need INITIAL_ADMIN_USER_IDS set

### Constraints
- **No Auto-Detection:** cannot infer team lead from channel (explicit registration required)
- **Single Lead:** current structure supports 1 lead only (multi-lead requires new ADR)

## Bootstrap Checklist

- [ ] Define INITIAL_ADMIN_USER_IDS env var (comma-separated, e.g., "aad-id-1,aad-id-2")
- [ ] startup hook: validate INITIAL_ADMIN_USER_IDS (error if missing)
- [ ] Implement team_lead_service.register_team_lead()
- [ ] Audit log: track team lead registration/transfer (actor, target, action)
- [ ] Documentation: operator guide for INITIAL_ADMIN_USER_IDS setup

## Example Environment Variables

```bash
# .env (production)
INITIAL_ADMIN_USER_IDS=8d8c6be0-8af4-4f9f-b5ea-8d3c2e5c3f4a,9e9d7cf1-9bg5-5g0g-c6fb-9e4d3f6d4g5b

# or empty (self-register only)
INITIAL_ADMIN_USER_IDS=
```

## References

- ADR-SEC-002: team-lead registration ACL (security perspective)
- Bot Framework Activity: from.aadObjectId (trusted source)
- AuditLog: action="team_lead_registered", "team_lead_transferred"
