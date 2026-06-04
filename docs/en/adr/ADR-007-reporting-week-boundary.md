---
id: ADR-007
title: Reporting Week Boundary: ISO Week, Thu 13:00 KST, UTC Storage
status: Accepted
date: 2026-06-04
---

# ADR-007: Reporting Week Boundary: ISO Week, Thu 13:00 KST, UTC Storage

## Status
Accepted

## Context

Report system operates on "weekly" basis. Must define:

1. **Week Identification:** how to represent week?
   - Monday start? Sunday start?
   - Which week does Monday Jan 1 belong to?

2. **Submission Deadline:** when is submission due?
   - Thu 13:00? (Korea time)
   - Midnight? (which timezone?)

3. **Timestamp Storage:** which timezone in DB?
   - UTC? Local (KST)?

## Decision

### 1. week_key: ISO 8601 (ISO week)
- Format: "YYYY-Www" (e.g., "2026-W23")
- ISO week starts Monday, W01 includes Jan 4
- Global standard, unambiguous

### 2. Deadline: Thu 13:00 KST
- Every Thursday 1:00 PM (Asia/Seoul timezone)
- Managed via Python zoneinfo or pytz
- Korea has no DST (UTC+9 fixed)

### 3. DB Timestamp: UTC Storage
- All submitted_at, created_at, updated_at stored in UTC
- Convert to required timezone on retrieval
- Prevents time confusion in distributed systems

## Rationale

### 1. ISO Week Clarity
- ISO 8601 is international standard
- Monday start aligns with business weeks
- "2026-W23" unambiguously refers to 2026 week 23
- Computation is deterministic

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Thu of 2026-W23
week_key = "2026-W23"
year, week = map(int, week_key.split("-W"))
# ISO week to date
from datetime import datetime, timedelta
jan4 = datetime(year, 1, 4)
week1_monday = jan4 - timedelta(days=jan4.weekday())
thursday = week1_monday + timedelta(weeks=week-1, days=3)
# thursday = 2026-06-04
```

### 2. Thu 13:00 KST Deadline
- Adequate time after morning work to finalize
- Minimal disruption to afternoon tasks
- Team lead can approve same afternoon
- Reasonable across organization schedule

### 3. UTC Storage Advantage
- Server timezone change preserves data consistency
- Supports multi-timezone teams (future)
- Cloud industry standard

```python
# store as UTC
submitted_at_utc = datetime.now(timezone.utc)

# convert to KST on retrieval
kst = ZoneInfo("Asia/Seoul")
submitted_at_kst = submitted_at_utc.astimezone(kst)
```

## Consequences

### Positive
- **Standardization:** ISO week is global standard
- **Clarity:** week_key unambiguously identifies week
- **Consistency:** UTC storage ensures distributed system stability
- **Maintainability:** timezone changes don't compromise data integrity

### Drawbacks
- **Timezone Calculation:** deadline judgment always server logic (never client)
- **Dev Complexity:** timezone management required (zoneinfo, pytz)
- **Testing:** boundary case testing mandatory (Thu 12:59:59, 13:00:00, 13:00:01)

### Constraints
- **Fixed Deadline:** all channels locked to Thu 13:00 KST (no per-channel adjustment)
- **Timezone Migration:** if organization relocates, new ADR required

## Implementation Checklist

- [ ] week_key calculation: get_week_key_for_date(date) → "YYYY-Www"
- [ ] deadline calculation: get_week_deadline(week_key) → datetime(UTC)
- [ ] submitted_after_deadline judgment: datetime.now(UTC) > get_week_deadline(week_key)
- [ ] DB: all timestamp columns UTC defined (datetime with timezone)
- [ ] Audit log: record deadline status (submitted_after_deadline boolean)
- [ ] Test: boundary Thu 12:59:59.999 vs 13:00:00.000

## Code Example

```python
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

class WeekUtils:
    @staticmethod
    def get_week_key(date: datetime) -> str:
        """Get ISO week key from date (e.g., '2026-W23')"""
        iso_cal = date.isocalendar()
        return f"{iso_cal.year}-W{iso_cal.week:02d}"

    @staticmethod
    def get_week_deadline(week_key: str) -> datetime:
        """Get Thu 13:00 KST for given week, return as UTC"""
        year, week = map(int, week_key.split("-W"))

        # Calculate Monday of that week
        jan4 = datetime(year, 1, 4)
        week1_monday = jan4 - timedelta(days=jan4.weekday())
        week_monday = week1_monday + timedelta(weeks=week-1)

        # Thursday is 3 days after Monday
        week_thursday = week_monday + timedelta(days=3)

        # Set to 13:00 KST
        kst = ZoneInfo("Asia/Seoul")
        deadline_kst = week_thursday.replace(hour=13, minute=0, second=0, microsecond=0)
        deadline_kst = deadline_kst.replace(tzinfo=kst)

        # Convert to UTC
        deadline_utc = deadline_kst.astimezone(timezone.utc)
        return deadline_utc

    @staticmethod
    def is_after_deadline(submitted_at: datetime) -> bool:
        """Check if submitted_at is after deadline (assumes UTC)"""
        week_key = WeekUtils.get_week_key(submitted_at.astimezone(ZoneInfo("Asia/Seoul")))
        deadline_utc = WeekUtils.get_week_deadline(week_key)
        return submitted_at > deadline_utc

# Usage
now_utc = datetime.now(timezone.utc)
week_key = WeekUtils.get_week_key(now_utc.astimezone(ZoneInfo("Asia/Seoul")))
# week_key = "2026-W23"

deadline_utc = WeekUtils.get_week_deadline(week_key)
# deadline_utc = 2026-06-04 04:00:00+00:00 (13:00 KST = 04:00 UTC)

is_late = WeekUtils.is_after_deadline(now_utc)
```

## References

- [ISO 8601 Week Date](https://en.wikipedia.org/wiki/ISO_week_date)
- [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html)
- [Python datetime](https://docs.python.org/3/library/datetime.html)
