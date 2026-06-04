---
id: ADR-SEC-006
title: No Proxy Submission: Reporter Identity Pinning (Security Perspective)
status: Accepted
date: 2026-06-04
---

# ADR-SEC-006: No Proxy Submission: Reporter Identity Pinning (Security Perspective)

## Status
Accepted

## Context

ADR-006 is technical decision, this ADR-SEC-006 is security perspective.

**No proxy submission is hardcoded invariant.**

## Decision

**activity.from.aadObjectId == report_slot.owner_aad_id must always hold. This invariant is immutable.**

### Validation Logic (Immutable)

```python
# within submission_service.submit()
if activity.from.aadObjectId != report_slot.owner_aad_id:
    # unconditionally reject
    raise PermissionDenied("No proxy submission allowed")
    # this logic cannot change without new ADR
```

## Rationale

### 1. Security Policy (Policy as Code)
- "no team-lead proxy submission" enforced in code
- Policy change requires ADR review (social contract)

### 2. Accountability
- Report author = submitter (always match)
- Author cannot be denied

### 3. Compliance
- Audit log: all submission recorded
- Cannot claim "team lead submitted, not me"

### 4. Social Contract
- Development team and organization agreement
- Hardcoded prevents "exception" workarounds

## Consequences

### Positive
- **Policy Enforcement:** code enforces policy
- **Immutability:** policy explicit and unchangeable
- **Audit:** all proxy attempts detected

### Drawbacks
- **Operational Rigidity:** hard to handle exceptions
- **Team Lead Burden:** can encourage but cannot force

## Violation Handling

**Violation attempt:**
```python
await audit_log_repo.log(
    channel_id=channel_id,
    action="proxy_submit_attempt",
    actor_aad_id=activity.from.aadObjectId,
    details={
        "target_owner_aad_id": report_slot.owner_aad_id,
        "week_key": week_key
    }
)
```

**Monitoring:**
- AuditLog.action = "proxy_submit_attempt"
- Regular audit reports generated
- Security team notified of anomalies

## Policy Change Procedure

If team-lead proxy submission needed in future:

1. **Write new ADR** (ADR-009 or equivalent)
2. **CTO approval**
3. **Security team audit**
4. **Compliance review**
5. **Code modification**
6. **Update audit log** (change action name)

## References

- ADR-006: no proxy submission (technical perspective)
- Policy: 05_project_decisions.md "no team-lead proxy"
