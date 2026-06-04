---
id: ADR-SEC-005
title: Channel Isolation Enforcement: ORM + Audit Log
status: Accepted
date: 2026-06-04
---

# ADR-SEC-005: Channel Isolation Enforcement: ORM + Audit Log

## Status
Accepted

## Context

ADR-002 defined channel_id as partition key. How do we **enforce** this?

Option 1: validate in service layer only (channel_id required param)
Option 2: enforce in ORM layer (ChannelScopedRepository)
Option 3: both (defense in depth)

## Decision

**Enforce in ORM layer, log cross-channel attempts in audit log.**

### Enforcement Mechanism

**ChannelScopedRepository base class:**
```python
class ChannelScopedRepository(Generic[T]):
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        """Find entity, MANDATORY channel_id"""
        stmt = select(self.model).where(
            self.model.channel_id == channel_id,
            self.model.id == id
        )
        return await session.scalar(stmt)

    # only find_all_for_channel exists, no find_all
    async def find_all_for_channel(self, channel_id: str) -> List[T]:
        """Find all for a channel, MANDATORY channel_id"""
        stmt = select(self.model).where(
            self.model.channel_id == channel_id
        )
        return await session.scalars(stmt).all()

    # only update_for_channel exists
    async def update_for_channel(
        self, channel_id: str, id: UUID, **updates
    ) -> Optional[T]:
        stmt = (
            update(self.model)
            .where(
                self.model.channel_id == channel_id,
                self.model.id == id
            )
            .values(**updates)
            .returning(self.model)
        )
        return await session.scalar(stmt)
```

### Cross-Channel Attempt Logging

```python
# Middleware in service layer
async def validate_channel_context(activity: Activity, request_channel_id: str):
    """
    Validate Activity channel_id matches request channel_id.
    Log if mismatch.
    """
    activity_channel_id = activity.channelData.teamsChannelId

    if activity_channel_id != request_channel_id:
        # Cross-channel attempt
        await audit_log_repo.log(
            channel_id=activity_channel_id,  # actual channel
            action="cross_channel_attempt",
            actor_aad_id=activity.from.aadObjectId,
            details={
                "requested_channel_id": request_channel_id,
                "actual_channel_id": activity_channel_id
            }
        )
        raise PermissionDenied(
            "Activity channel does not match request"
        )
```

## Rationale

### 1. ORM Layer Enforcement Advantages
- Developers cannot accidentally query without channel_id
- Method signature enforces (IDE autocomplete helps)
- Code review catches omissions

### 2. Audit Log Importance
- Detect cross-channel attempts
- Evidence for security incident response
- Identify malicious users

### 3. Defense in Depth
- Service layer: business logic validation
- ORM layer: data access enforcement
- Audit log: incident recording

## Consequences

### Positive
- **Security:** cross-channel access technically impossible
- **Dev Safety:** method signature enforcement
- **Audit:** cross-channel attempts logged

### Drawbacks
- **Complexity:** all repository methods pass channel_id
- **Testing:** isolated test data per channel_id

## Implementation Checklist

- [ ] Define ChannelScopedRepository base class
- [ ] All repositories inherit ChannelScopedRepository
- [ ] Remove find_all, update (without channel_id)
- [ ] Implement ActivityValidator middleware
- [ ] Audit log schema: action="cross_channel_attempt"
- [ ] Test: channel_id mismatch cases

## Audit Log Example

```json
{
  "channel_id": "channel-A",
  "action": "cross_channel_attempt",
  "actor_aad_id": "user-123",
  "details": {
    "requested_channel_id": "channel-B",
    "actual_channel_id": "channel-A"
  },
  "timestamp": "2026-06-04T10:30:00Z"
}
```

## References

- ADR-002: channel isolation as partition key (design)
- ChannelScopedRepository: base class pattern
