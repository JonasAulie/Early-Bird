"""GitHub Actions cron is always UTC, but the desired run times (07:32,
08:02) are in Oslo local time, which shifts between CET and CEST.
Rather than maintaining two sets of cron entries, the workflow fires at
every UTC time that could possibly correspond to one of the two slots
across both DST states, and this guard makes each firing a no-op unless
the *actual* current Oslo time is close to one of the real target slots.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
TARGET_SLOTS = [(7, 32), (8, 2)]
TOLERANCE_MINUTES = 12


def should_run_now(now_utc: datetime = None) -> bool:
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    local = now_utc.astimezone(OSLO)
    local_minutes = local.hour * 60 + local.minute
    for hour, minute in TARGET_SLOTS:
        target_minutes = hour * 60 + minute
        if abs(local_minutes - target_minutes) <= TOLERANCE_MINUTES:
            return True
    return False
