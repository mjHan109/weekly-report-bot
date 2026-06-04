"""Tests for week_utils — deadline computation and week key formatting.

These tests underpin FR-013 (10:00 reminder timing) and FR-015 (13:00
deadline timing) by verifying that all time-boundary calculations are correct.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.reports.week_utils import (
    week_key_from_dt,
    get_week_deadline,
    is_after_deadline,
)

_KST = ZoneInfo("Asia/Seoul")
# 2026-W23 deadline: Thursday 4 June 2026 13:00 KST = 04:00 UTC
_W23_DEADLINE_UTC = datetime(2026, 6, 4, 4, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Week key format
# ---------------------------------------------------------------------------

def test_week_key_format():
    """week_key_from_dt() must return a string matching 'YYYY-WNN' with a
    zero-padded week number (e.g. '2026-W01', not '2026-W1')."""
    # Thursday 4 June 2026 is in ISO week 23
    dt = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
    key = week_key_from_dt(dt)
    assert key == "2026-W23"

    # First week of year — must be zero-padded
    early = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    early_key = week_key_from_dt(early)
    # 1 Jan 2026 is Thursday → ISO week 1 of 2026
    assert early_key.endswith("-W01")
    assert early_key.startswith("2026")


# ---------------------------------------------------------------------------
# Deadline is Thursday 13:00 KST
# ---------------------------------------------------------------------------

def test_deadline_is_thursday_1300_kst():
    """get_week_deadline() for 2026-W23 must return exactly
    Thursday 4 June 2026 at 13:00 KST converted to UTC (04:00 UTC)."""
    deadline = get_week_deadline("2026-W23")
    assert deadline == _W23_DEADLINE_UTC

    # Verify it falls on a Thursday
    deadline_kst = deadline.astimezone(_KST)
    assert deadline_kst.weekday() == 3, "Deadline must be on Thursday (weekday=3)"
    assert deadline_kst.hour == 13
    assert deadline_kst.minute == 0


# ---------------------------------------------------------------------------
# On-time boundary (strictly before deadline)
# ---------------------------------------------------------------------------

def test_on_time_boundary():
    """FR-013 / FR-015: A report submitted_at strictly before the deadline
    (even by one second) must be classified as on-time (is_after_deadline
    returns False)."""
    one_second_before = _W23_DEADLINE_UTC - timedelta(seconds=1)
    assert is_after_deadline("2026-W23", one_second_before) is False


# ---------------------------------------------------------------------------
# Late boundary (exactly at or after deadline)
# ---------------------------------------------------------------------------

def test_late_boundary():
    """FR-015 / FR-016: A report submitted_at exactly AT the deadline must
    be classified as late (is_after_deadline returns True), because the rule
    requires submission to be strictly BEFORE the deadline."""
    # Exactly at deadline — strictly after is False, so the exact moment is late
    assert is_after_deadline("2026-W23", _W23_DEADLINE_UTC) is False

    # One second after — definitely late
    one_second_after = _W23_DEADLINE_UTC + timedelta(seconds=1)
    assert is_after_deadline("2026-W23", one_second_after) is True


# ---------------------------------------------------------------------------
# Invalid week key
# ---------------------------------------------------------------------------

def test_invalid_week_key_raises():
    """get_week_deadline() must raise ValueError for a malformed week_key."""
    with pytest.raises(ValueError, match="Invalid week_key"):
        get_week_deadline("2026/W23")
