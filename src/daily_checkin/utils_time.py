from __future__ import annotations

from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo


def _ensure_utc(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        return dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(timezone.utc)


def local_date_for(tz_name: str, dt_utc: datetime) -> date:
    tz = ZoneInfo(tz_name)
    return _ensure_utc(dt_utc).astimezone(tz).date()


def combine_local_to_utc(tz_name: str, d: date, t: time) -> datetime:
    tz = ZoneInfo(tz_name)
    local_dt = datetime.combine(d, t, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def add_minutes(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)


def add_hours(dt: datetime, hours: int) -> datetime:
    return dt + timedelta(hours=hours)