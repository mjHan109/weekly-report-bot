---
id: ADR-006
title: No Proxy Submission: Reporter Identity Pinning
status: Accepted
date: 2026-06-04
---

# ADR-006: No Proxy Submission: Reporter Identity Pinning

## Status
Accepted

## Context

Explicitly defined in project requirements:
**Team leads cannot submit reports on behalf of non-submitters. Non-submitters must submit themselves, even if late.**

Technical implementation approaches:

Option 1: team lead can submit under someone else's name (tracking record only)
Option 2: team lead proxy submission impossible (hardcoded invariant)
Option 3: policy configurable per channel

## Decision

**Proxy submission is an impossible hardcoded invariant. activity.from.aadObjectId == PersonalReport.owner_aad_id must always hold.**

Within submission_service.submit():
```python
if activity.from.aadObjectId != report_slot.owner_aad_id:
    raise PermissionDenied("No proxy submission allowed")
```

Violation results in:
- HTTP 403 Forbidden response
- AuditLog entry: action="proxy_submit_attempt"
- Security team notification (if needed)

## Rationale

### 1. Accountability Tracking
- Must know who submitted the report
- Team lead submitting under another's name breaks traceability
- Organizational compliance requirement

### 2. Report Trustworthiness
- Need to distinguish "I wrote this" from "team lead wrote this for me"
- Proxy submissions cannot guarantee content accuracy
- Risk of team lead bias in authoring

### 3. Policy Clarity
- Requirement explicitly states "self-submission"
- Operational policy: non-submitters bear responsibility
- Team lead can encourage/remind, but not submit

### 4. Audit Trail
- All submission records include aadObjectId
- Usable as evidence in legal disputes

## Consequences

### Positive
- **Clear Accountability:** no ambiguity about who submitted
- **Policy Enforcement:** code itself implements policy
- **Audit:** proxy submission attempts detectable

### Drawbacks
- **Team Lead Burden:** can encourage but cannot force submission
- **No Deadline Extension:** cannot submit on behalf if person refuses
- **Operational Inflexibility:** difficult to handle edge cases (new ADR needed)

### Constraints
- **Change Policy:** invariant is hardcoded, code changes required to modify
- **Future Features:** "team lead substitute submission" would require new ADR

## Implementation Example

```python
# Layer 3: Service
class SubmissionService:
    async def submit(
        self,
        channel_id: str,
        activity: Activity,  # Bot Framework Activity
        week_key: str,
        content: str
    ) -> PersonalReport:
        # Sender extracted from Activity
        owner_aad_id = activity.from.aadObjectId

        # Look up report slot (for this owner_aad_id)
        report_slot = await self.slot_repo.find_by_channel_owner_week(
            channel_id,
            owner_aad_id,
            week_key
        )

        if not report_slot:
            raise NotFound("No report slot for this user")

        # ADR-006: no proxy submission
        # Activity sender and slot owner must match exactly
        if activity.from.aadObjectId != report_slot.owner_aad_id:
            # security audit log
            await self.audit_log_repo.log(
                channel_id=channel_id,
                action="proxy_submit_attempt",
                actor_aad_id=activity.from.aadObjectId,
                details={
                    "target_owner_aad_id": report_slot.owner_aad_id,
                    "week_key": week_key
                }
            )
            raise PermissionDenied(
                "Proxy submission not allowed. Please submit your own report."
            )

        # Determine submitted_after_deadline
        now_kst = datetime.now(timezone("Asia/Seoul"))
        deadline = self._get_week_deadline(week_key)  # Thu 13:00 KST
        submitted_after_deadline = now_kst > deadline

        # Create PersonalReport
        report = PersonalReport(
            channel_id=channel_id,
            report_slot_id=report_slot.id,
            owner_aad_id=owner_aad_id,
            week_key=week_key,
            content=content,
            submitted_at=now_kst,
            submitted_after_deadline=submitted_after_deadline,
            status=ReportStatus.SUBMITTED
        )

        await self.report_repo.save(report)

        # Late submit event
        if submitted_after_deadline:
            await self.event_bus.emit(LateSubmissionEvent(...))

        return report
```

## References

- [05_project_decisions.md](../../05_project_decisions.md) — "no team-lead proxy submission" decision
- ADR-SEC-006: no proxy submission (security perspective)
- AuditLog: proxy_submit_attempt tracking
