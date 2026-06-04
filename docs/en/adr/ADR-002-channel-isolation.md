---
id: ADR-002
title: Channel Isolation: channel_id as Partition Key
status: Accepted
date: 2026-06-04
---

# ADR-002: Channel Isolation: channel_id as Partition Key

## Status
Accepted

## Context

Project requirement: each Teams channel operates an independent team report system. Data from channel A must never be accessible to users in channel B.

Implementation approaches:
1. **Application Layer:** channel_id validation in each API endpoint
2. **ORM Layer:** channel_id filtering in all queries
3. **DB Partition Layer:** physical partitioning (cloud-native consideration)

Which layer(s) should enforce this?

## Decision

**Define channel_id as partition key on all tenant-scoped DB tables, and enforce via ChannelScopedRepository base class at ORM layer.**

- All data retrieval methods take channel_id as first argument.
- Queries without channel_id are impossible via method signature.
- Extract channel_id only from Bot Framework Activity (trusted source).
- Ignore card payload and user input channel_id.

## Rationale

### 1. Defense in Depth
- Application code bugs possible → ORM enforcement provides secondary defense
- ORM query omissions possible → DB partitioning provides tertiary defense

### 2. ORM Method Signature Enforcement
```python
class ChannelScopedRepository:
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        # channel_id mandatory, cannot omit

    async def find_all(self, channel_id: str) -> List[T]:
        # this method doesn't exist; developers forced to use find_all_for_channel
```

- Method signature enforces channel_id
- IDE autocomplete cannot suggest channel_id-less calls
- Prevents developer mistakes

### 3. Bot Framework Activity is Trusted Source
- Bot Framework provides Microsoft-verified Activity
- Activity.channelData.teamsChannelId is the channel where bot received message
- Activity.from.aadObjectId is bot-verified sender
- Never trust client payload channel_id

### 4. Audit Logging
- Cross-channel access attempts logged in AuditLog
- Security team can detect anomalies

## Consequences

### Positive
- **Security:** channel isolation guaranteed, accidental cross-channel access impossible
- **Dev Reliability:** ORM auto-filters, query omissions prevented
- **Audit:** all cross-channel attempts logged
- **Scalability:** works with cloud-native DBs (Spanner, DynamoDB) using partition key

### Drawbacks
- **Performance:** all queries filtered by channel_id → index strategy critical
- **Complexity:** all repository methods must pass channel_id
- **Testing:** isolated test data management per channel_id

### Constraints
- Cross-channel report comparison impossible (e.g., dept-level comparison)
- Future multi-channel analytics impossible (new ADR required)

## Implementation Example

```python
# Layer 4: Domain/Repository
class ChannelScopedRepository(Generic[T]):
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        return await session.scalar(
            select(self.model)
            .where(self.model.channel_id == channel_id)
            .where(self.model.id == id)
        )

    async def find_all_for_channel(self, channel_id: str) -> List[T]:
        return await session.scalars(
            select(self.model).where(self.model.channel_id == channel_id)
        ).all()

# Layer 3: Service
class SubmissionService:
    async def submit(self, channel_id: str, owner_aad_id: str,
                     week_key: str, content: str) -> PersonalReport:
        # channel_id extracted only from Bot Framework Activity
        # passed as first argument in repository calls
        existing_report = await self.report_repo.find_by_channel_owner_week(
            channel_id,  # first argument: mandatory
            owner_aad_id,
            week_key
        )
        ...

# Layer 2: API
@router.post("/api/reports/submit")
async def submit_report(activity: Activity, request: SubmitRequest):
    # Extract channel_id from Activity only
    channel_id = activity.channelData.teamsChannelId
    owner_aad_id = activity.from.aadObjectId

    # Ignore request payload channel_id
    report = await submission_service.submit(
        channel_id,  # Activity source
        owner_aad_id,
        request.week_key,
        request.content
    )
```

## References

- ADR-SEC-005: channel isolation enforcement (security perspective)
- [docs/ko/phase_outputs/phase-1-architecture.md](../../phase_outputs/phase-1-architecture.md) — Layer 4 reference
