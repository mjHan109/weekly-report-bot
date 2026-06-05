"""Week-key utilities and deadline computation.

All deadlines are computed as Thursday 13:00 Asia/Seoul, then stored as UTC.

Week key format: "YYYY-WNN"  (ISO year + zero-padded ISO week number)
Example: "2026-W23"

Python's datetime.isocalendar() is used for ISO week arithmetic.
zoneinfo is built-in from Python 3.9; this module targets Python 3.12+.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")

# Thursday is weekday 3 (Monday=0 in isoweekday it's 4, but we use weekday())
_DEADLINE_WEEKDAY = 3       # Thursday (0=Mon … 6=Sun via .weekday())
_DEADLINE_HOUR_KST = 13     # 13:00 KST


def week_key_from_dt(dt: datetime) -> str:
    """Return the ISO week key for the week containing ``dt``.

    Args:
        dt: Any timezone-aware or naive datetime.

    Returns:
        String in "YYYY-WNN" format, e.g. "2026-W23".
    """
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def current_week_key() -> str:
    """Return the ISO week key for the current week (UTC now)."""
    return week_key_from_dt(datetime.now(tz=timezone.utc))


def previous_week_key() -> str:
    """Return the ISO week key for last week."""
    return week_key_from_dt(datetime.now(tz=timezone.utc) - timedelta(weeks=1))


def get_week_deadline(week_key: str) -> datetime:
    """Compute the absolute deadline (Thursday 13:00 KST) for ``week_key``.

    The returned datetime is timezone-aware UTC.

    Args:
        week_key: ISO week string, e.g. "2026-W23".

    Returns:
        UTC datetime representing Thursday 13:00 Asia/Seoul of that week.

    Raises:
        ValueError: If ``week_key`` does not match the expected format.
    """
    try:
        year_str, week_str = week_key.split("-W")
        year = int(year_str)
        week = int(week_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid week_key {week_key!r}. Expected format 'YYYY-WNN'."
        ) from exc

    # ISO week 1 of a year always contains January 4.
    # The Thursday of week W is: Jan 4 + (W-1)*7 days, then adjusted to Thursday.
    jan_4 = datetime(year, 1, 4, tzinfo=_KST)
    # Monday of ISO week 1
    monday_of_week1 = jan_4 - timedelta(days=jan_4.weekday())
    # Monday of target week
    monday_of_target_week = monday_of_week1 + timedelta(weeks=week - 1)
    # Thursday of target week
    thursday_kst = monday_of_target_week + timedelta(days=_DEADLINE_WEEKDAY)
    # Set time to 13:00:00 KST
    deadline_kst = thursday_kst.replace(
        hour=_DEADLINE_HOUR_KST, minute=0, second=0, microsecond=0
    )
    # Convert to UTC
    return deadline_kst.astimezone(timezone.utc)


def is_after_deadline(week_key: str, reference_utc: datetime | None = None) -> bool:
    """Return True if ``reference_utc`` is strictly after the week's deadline.

    Args:
        week_key:       ISO week key, e.g. "2026-W23".
        reference_utc:  UTC datetime to compare; defaults to now.

    Returns:
        True if the reference time is past Thursday 13:00 KST.
    """
    if reference_utc is None:
        reference_utc = datetime.now(tz=timezone.utc)
    return reference_utc > get_week_deadline(week_key)
