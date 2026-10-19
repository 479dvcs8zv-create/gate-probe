#!/usr/bin/env python3
"""NYSE trading calendar used to decide which completed US session a snapshot must contain.

Holidays and early closes: https://www.nyse.com/markets/hours-calendars (read 2026-10-19).
Outside the listed years the calendar refuses to answer (CALENDAR_NOT_COVERED) instead of guessing.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
NYSE_HOLIDAYS = {
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03',
    '2026-09-07', '2026-11-26', '2026-12-25',
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05',
    '2027-09-06', '2027-11-25', '2027-12-24',
}
NYSE_EARLY_CLOSE = {'2026-11-27', '2026-12-24', '2027-11-26'}   # 13:00 close
FIRST_DAY, LAST_DAY = dt.date(2026, 1, 1), dt.date(2027, 12, 31)
SETTLE_MINUTES = 15            # a close counts as completed 15 minutes after the bell (same as the site reader)
PUBLISH_GRACE_HOURS = 8        # cron 23:35 UTC + observed GitHub delay of 1.9-2.5 h ~= close + 6.1 h in summer


def is_session(day):
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError('CALENDAR_NOT_COVERED')
    return day.weekday() < 5 and day.isoformat() not in NYSE_HOLIDAYS


def session_settled_utc(day):
    close = dt.time(13, SETTLE_MINUTES) if day.isoformat() in NYSE_EARLY_CLOSE else dt.time(16, SETTLE_MINUTES)
    return dt.datetime.combine(day, close, tzinfo=NY).astimezone(dt.timezone.utc)


def expected_latest_session(now, grace_hours=PUBLISH_GRACE_HOURS):
    """Latest NYSE session whose close (plus publication grace) is already in the past at `now`."""
    day = now.astimezone(NY).date()
    for _ in range(15):
        if is_session(day) and now >= session_settled_utc(day) + dt.timedelta(hours=grace_hours):
            return day
        day -= dt.timedelta(days=1)
    raise ValueError('NO_SESSION_FOUND')
