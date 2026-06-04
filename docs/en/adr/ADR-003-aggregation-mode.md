---
id: ADR-003
title: Aggregation Mode Decision: At Deadline (13:00)
status: Accepted
date: 2026-06-04
---

# ADR-003: Aggregation Mode Decision: At Deadline (13:00)

## Status
Accepted

## Context

TeamReport.aggregation_mode is either AUTO or MANUAL.

- **AUTO:** all team members submitted by Thu 13:00 → automatic LLM aggregation starts at 13:00
- **MANUAL:** late submission occurs after Thu 13:00 → team lead manually initiates aggregation

**Question:** when is mode decided?

Option 1: decide once at 13:00 (immutable afterward)
Option 2: decide dynamically on each late submission (AUTO → MANUAL possible)
Option 3: start as MANUAL (team lead always in control)

## Decision

**aggregation_mode is decided once at 13:00. No reverse transition from MANUAL → AUTO afterward.**

When deadline_service.check_deadline() is called (Thu 13:00 KST):
- If all team members submitted → aggregation_mode = AUTO (automatic LLM aggregation starts)
- If any missing → aggregation_mode = MANUAL (team lead waits to decide)

If late submission occurs post-13:00:
- TeamReport.status can transition AUTO_AGGREGATING → MANUAL_PENDING
- But aggregation_mode is already fixed as MANUAL
- Team lead calls aggregation_service.aggregate() manually

## Rationale

### 1. Prevent Race Condition
- Submissions just before and after 13:00 create ambiguity in AUTO vs MANUAL judgment
- Single decision point makes logic explicit and idempotent

### 2. Preserve Team-Lead Control
- Post-deadline, team lead must judge required trustworthiness level
- Prevents "why auto-aggregate with only 1 missing?" complaints
- Team lead retains final authority

### 3. State Machine Simplicity
```
Before 13:00: COLLECTING
At exactly 13:00:
  - All submitted: enter AUTO_AGGREGATING, LLM auto-aggregates
  - Anyone missing: enter MANUAL_PENDING, team lead waits

After 13:00 late submission:
  - aggregation_mode already decided (immutable)
  - TeamReport.status updated only (state machine transition)
```

### 4. Operational Policy Clarity
- "Decide at 13:00 based on submission status" is easy to understand
- Easy to document and explain to users

## Consequences

### Positive
- **Clarity:** when decision happens is explicit
- **Predictability:** users know pre-13:00 whether auto vs manual
- **Simplicity:** state machine logic straightforward

### Drawbacks
- **Rigidity:** decision at 13:00 is immutable
- **Team-Lead Burden:** MANUAL mode requires team lead to click aggregate
- **Late Submission Complexity:** logic split before/after 13:00 (needs robust test coverage)

### Constraints
- **Deadline Time Immutable:** requirement fixes 13:00 KST
- **No Alternate Policy:** once decided, no override until next week

## State Machine (13:00 Centric)

```
Before 13:00:
  COLLECTING (awaiting all submissions)
    │
    ├─ (person submits before 13:00)
    │   → PersonalReport.submitted_at logged (pre-13:00)
    │
    └─ (person misses 13:00)
        → COLLECTING remains

Exactly 13:00 (deadline_service.check_deadline() called):
  Check: do all ChannelReportTargets have PersonalReport?
    │
    ├─ YES → aggregation_mode = AUTO
    │        TeamReport.status = AUTO_AGGREGATING
    │        aggregation_service.aggregate() starts
    │
    └─ NO → aggregation_mode = MANUAL
            TeamReport.status = MANUAL_PENDING
            team lead card: "N missing, manual aggregate required"

After 13:00:
  aggregation_mode already decided (immutable)

  Late submission occurs:
    → aggregation_mode = MANUAL (already decided)
    → TeamReport.status updated (stays/transitions in MANUAL_PENDING)
    → team lead notification sent
```

## References

- ADR-007: reporting week boundary (week_key, 13:00 deadline)
- [phase-1-architecture.md](../../phase_outputs/phase-1-architecture.md) — aggregation state machine section
