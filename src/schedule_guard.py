"""GitHub Actions cron is always UTC, but the desired run times (16:00 the
day before, 07:32, 08:02) are in Oslo local time, which shifts between CET
and CEST. Rather than maintaining two sets of cron entries, the workflow
(and the external cron-job.org triggers) fire at every UTC/Oslo time that
could possibly correspond to one of the three slots, and this guard makes
each firing a no-op unless the *actual* current Oslo time and weekday is
close to one of the real target slots.

Three sends per edition: a 16:00 heads-up the business day before, then
07:32 and 08:02 on the day the edition is "for". Each is an independent
scan/send (no shared state, no dedup against the other slots) -- the
16:00 preview can legitimately differ from the 07:32/08:02 morning
edition if news breaks overnight.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
MORNING_SLOTS = [(7, 32), (8, 2)]
PREVIEW_SLOT = (16, 0)
TOLERANCE_MINUTES = 12

# datetime.weekday(): Monday=0 ... Sunday=6.
MORNING_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri: the edition itself
PREVIEW_WEEKDAYS = {6, 0, 1, 2, 3}  # Sun-Thu: the day before a Mon-Fri edition


def should_run_now(now_utc: datetime = None) -> bool:
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    local = now_utc.astimezone(OSLO)
    weekday = local.weekday()
    local_minutes = local.hour * 60 + local.minute

    if weekday in MORNING_WEEKDAYS:
        for hour, minute in MORNING_SLOTS:
            target_minutes = hour * 60 + minute
            if abs(local_minutes - target_minutes) <= TOLERANCE_MINUTES:
                return True

    if weekday in PREVIEW_WEEKDAYS:
        hour, minute = PREVIEW_SLOT
        target_minutes = hour * 60 + minute
        if abs(local_minutes - target_minutes) <= TOLERANCE_MINUTES:
            return True

    return False
