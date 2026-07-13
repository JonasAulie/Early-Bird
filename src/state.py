"""Persists (a) which items have already been emailed, so repeat runs don't
re-process the same raw item, and (b) the running list of entries already
sent so far today, so a later same-morning run's email can include what an
earlier run already sent instead of only its own delta (see main.py -- the
07:32 and 08:02 Oslo runs are meant to read as one cumulative morning digest,
not two independent partial ones). State is a JSON file committed back to
the repo by the GitHub Action after each run (see .github/workflows/early-bird.yml).
"""
import hashlib
import json
from pathlib import Path
from typing import List, Dict

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"


def item_id(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def _load_raw() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def load_seen() -> set:
    return set(_load_raw().get("seen_ids", []))


def load_today_entries(today: str) -> List[Dict]:
    """Entries already sent earlier today (Oslo-local calendar date string
    `today`, e.g. "2026-07-14"). Returns [] once the date has rolled over --
    each new day starts its cumulative digest fresh."""
    digest = _load_raw().get("today_digest") or {}
    if digest.get("date") != today:
        return []
    return digest.get("entries", [])


def save_seen(seen_ids: set, today: str, today_entries: List[Dict], max_keep: int = 2000):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep the file bounded; we only need the last few days of history
    # for dedup purposes, not a full archive.
    trimmed = list(seen_ids)[-max_keep:]
    payload = {
        "seen_ids": trimmed,
        "today_digest": {"date": today, "entries": today_entries},
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
