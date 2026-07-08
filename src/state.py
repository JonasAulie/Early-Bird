"""Persists which items have already been emailed, so the 4 daily runs
don't repeat themselves. State is a JSON file committed back to the repo
by the GitHub Action after each run (see .github/workflows/early-bird.yml).
"""
import hashlib
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"


def item_id(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def load_seen() -> set:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return set()
    return set(data.get("seen_ids", []))


def save_seen(seen_ids: set, max_keep: int = 2000):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep the file bounded; we only need the last few days of history
    # for dedup purposes, not a full archive.
    trimmed = list(seen_ids)[-max_keep:]
    STATE_PATH.write_text(json.dumps({"seen_ids": trimmed}, indent=2))
