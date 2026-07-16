"""GitHub Actions cron is always UTC, but the desired run times (16:00 the
day before, 07:32) are in Oslo local time, which shifts between CET
and CEST. Rather than maintaining two sets of cron entries, the workflow
(and the external cron-job.org triggers) fire at every UTC/Oslo time that
could possibly correspond to one of the two slots, and this guard makes
each firing a no-op unless the *actual* current Oslo time and weekday is
close to one of the real target slots.

Two sends per edition: a 16:00 heads-up the business day before, then
07:32 on the day the edition is "for". Each is an independent
scan/send (no shared state, no dedup against the other slot) -- the
16:00 preview can legitimately differ from the 07:32 morning
edition if news breaks overnight.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
MORNING_SLOTS = [(7, 32)]
PREVIEW_SLOT = (16, 0)
TOLERANCE_MINUTES = 12

# datetime.weekday(): Monday=0 ... Sunday=6.
MORNING_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri: the edition itself
PREVIEW_WEEKDAYS = {6, 0, 1, 2, 3}  # Sun-Thu: the day before a Mon-Fri edition


def _within_slot(local_minutes: int, hour: int, minute: int) -> bool:
    target_minutes = hour * 60 + minute
    return abs(local_minutes - target_minutes) <= TOLERANCE_MINUTES


def is_preview_slot(now_utc: datetime = None) -> bool:
    """True when `now_utc` is the 16:00 day-before preview firing specifically
    (not just any Sun-Thu firing -- the time-of-day tolerance too). main.py
    needs to know *which* of the three sends is running so it can point the
    recency cutoff at the edition the preview is actually for (tomorrow),
    not at today -- so this is exposed rather than kept private to
    should_run_now."""
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    local = now_utc.astimezone(OSLO)
    if local.weekday() not in PREVIEW_WEEKDAYS:
        return False
    local_minutes = local.hour * 60 + local.minute
    return _within_slot(local_minutes, *PREVIEW_SLOT)


def should_run_now(now_utc: datetime = None) -> bool:
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    local = now_utc.astimezone(OSLO)
    weekday = local.weekday()
    local_minutes = local.hour * 60 + local.minute

    if weekday in MORNING_WEEKDAYS:
        for hour, minute in MORNING_SLOTS:
            if _within_slot(local_minutes, hour, minute):
                return True

    return is_preview_slot(now_utc)
