"""Loads the merged company watchlist used by the fetcher."""
import json
from pathlib import Path

WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"


def load_companies():
    data = json.loads(WATCHLIST_PATH.read_text())
    return data["companies"]
