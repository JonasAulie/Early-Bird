"""One-off diagnostic: cross-check why real Early Bird items were missed by
the automated scanner today. Jonas's real issue had 7 items; the bot sent
Var Energi, OKEA, Bonheur (+ TGS the day before) but missed Baker Hughes,
NorAm Drilling, Equinor, and the Oil/EIA inventory item.

Dumps the raw Newsweb list for NORAM and EQNR (both have a working ticker)
to see whether the relevant messages are even being returned, with what
publish time, and whether they're already sitting in state/seen.json.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import json
from pathlib import Path

from src.fetch_newsweb import fetch_issuer_messages
from src.state import load_seen, item_id

SEEN_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"


def probe():
    seen = load_seen()
    print(f"{len(seen)} ids currently in state/seen.json\n")

    for issuer, label in [("NORAM", "NorAm Drilling"), ("EQNR", "Equinor")]:
        print(f"=== {label} (issuer={issuer}) ===")
        items = fetch_issuer_messages(issuer)
        print(f"{len(items)} messages returned from Newsweb list endpoint:")
        for it in items:
            iid = item_id(it["url"], it["title"])
            already_seen = iid in seen
            print(f"  published={it['published']!r}  already_seen={already_seen}  "
                  f"title={it['title'][:90]!r}")
            if it.get("summary"):
                print(f"    summary/body snippet: {it['summary'][:200]!r}")
        print()


if __name__ == "__main__":
    probe()
