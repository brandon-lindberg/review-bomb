"""Helpers for Tokyo-local date handling."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def tokyo_today() -> date:
    """Return today's date in Asia/Tokyo."""
    return datetime.now(TOKYO_TZ).date()


def tokyo_tomorrow_start_utc() -> datetime:
    """Return the UTC instant when the next Tokyo day begins."""
    tomorrow = tokyo_today() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=TOKYO_TZ).astimezone(timezone.utc)


def to_tokyo_date(value: date | datetime | None) -> date | None:
    """Convert a datetime to its Tokyo-local calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(TOKYO_TZ).date()
    return value
