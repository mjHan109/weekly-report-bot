---
id: ADR-SEC-003
title: Mail Send Triple-Gate: Status + Completeness + Authority
status: Accepted
date: 2026-06-04
---

# ADR-SEC-003: Mail Send Triple-Gate: Status + Completeness + Authority

## Status
Accepted

## Context

Before sending aggregated team report via mail, verify:

1. **Status Gate:** is TeamReport.status == AWAITING_APPROVAL?
2. **Completeness Gate:** did all team members submit?
3. **Authority Gate:** is actor the team lead?

**Question:** if gates only displayed on client card, can forged card state enable unauthorized mail send?

## Decision

**Server re-verifies all 3 conditions immediately pre-send. Card state is never trusted.**

```python
async def send_team_report(
    channel_id: str,
    team_report_id: UUID,
    actor_aad_id: str,  # from Activity
    activity: Activity
) -> Mail:
    # Gate 1: status verification
    team_report = await team_report_repo.find_by_id(channel_id, team_report_id)
    if team_report.status != TeamReportStatus.AWAITING_APPROVAL:
        raise ConflictError("Report not in approval-waiting state")

    # Gate 2: completeness verification
    targets = await channel_target_repo.find_all_for_channel(channel_id)
    for target in targets:
        report = await personal_report_repo.find_by_channel_owner_week(
            channel_id, target.target_aad_id, team_report.week_key
        )
        if not report or report.status != ReportStatus.SUBMITTED:
            raise ConflictError(f"Missing report from {target.target_aad_id}")

    # Gate 3: authority verification
    channel = await channel_repo.find_by_channel_id(channel_id)
    if actor_aad_id != channel.team_lead_aad_id:
        raise PermissionDenied("Not authorized as team lead")

    # all gates passed → send mail
    mail = await mail_send_service.send(channel_id, team_report_id, actor_aad_id)
    return mail
```

## Rationale

### 1. Prevent State Replay Attack
- Client card state can be forged
- Browser dev tools can modify card JSON
- Attempt to fake "AWAITING_APPROVAL" state to send mail

### 2. Trust Server State Only
- Server-managed state is authoritative
- Client state is display only

### 3. Completeness Re-verification
- Prevent race condition: personal report added post-gate check
- Confirm all reports exist immediately pre-send

### 4. Authority Re-verification
- Re-verify Activity to prevent authority forgery
- Prevent old Activity from old team lead sending mail

## Consequences

### Positive
- **Security:** state forgery cannot send mail
- **Data Integrity:** completeness guaranteed
- **Authority:** only team lead can send

### Drawbacks
- **Performance:** 3 DB lookups pre-send
- **Complexity:** 3-condition verification logic
- **Deadlock Risk:** lock contention under high concurrency

### Constraints
- **Race Condition:** if report added between completeness check and send?
  → Transaction or optimistic lock needed

## Implementation Details

### Transaction Protection

```python
async def send_team_report(...) -> Mail:
    async with db.transaction():
        # Gate 1, 2, 3 verification
        ...

        # send mail (Graph API)
        # if fails, transaction rollbacks
        ...

        # update TeamReport.status = MAIL_SENT
        ...
```

### Optimistic Lock

```python
class TeamReport:
    version: int  # optimistic lock

async def send_team_report(...):
    # ... gates ...

    # UPDATE with version check
    updated = await team_report_repo.update_with_version(
        channel_id,
        team_report_id,
        new_status=TeamReportStatus.MAIL_SENT,
        expected_version=team_report.version
    )

    if not updated:
        raise ConflictError("Report was modified")
```

## Audit Logging

- action: "mail_send_attempted"
- gates_passed: [1, 2, 3] or specific failure
- actor_aad_id: attempted actor
- team_report_id: target report

## References

- ADR-SEC-003 mail send triple-gate (security enforcer)
