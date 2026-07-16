"""One-off diagnostic: cross-check why real Early Bird items were missed by
the automated scanner today. Jonas's real issue had 7 items; the bot sent
Var Energi, OKEA, Bonheur (+ TGS the day before) but missed Baker Hughes,
NorAm Drilling, and Equinor.

v2: after fixing fetch_newsweb.py to always pass an explicit date range
(previously the undated call returned 0 messages for both EQNR and NORAM
despite same-day publications), a full production run STILL showed 0
candidates for either. This dumps the complete (untruncated) message list
for both issuers through the real fetch_issuer_messages() + recency check,
to see exactly what's being returned now and why it's not passing through.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
from datetime import datetime, timezone

from src.fetch_newsweb import fetch_issuer_messages
from src.main import lookback_cutoff, is_recent_enough
from src.state import load_seen, item_id


def probe():
    seen = load_seen()
    now = datetime.now(timezone.utc)
    cutoff = lookback_cutoff(now)
    print(f"now={now.isoformat()}  cutoff={cutoff.isoformat()}\n")

    for issuer, label in [("EQNR", "Equinor"), ("NORAM", "NorAm Drilling")]:
        print(f"=== {label} (issuer={issuer}) ===")
        items = fetch_issuer_messages(issuer)
        print(f"{len(items)} messages returned:")
        for it in items:
            iid = item_id(it["url"], it["title"])
            recent = is_recent_enough(it["published"], cutoff, now)
            already_seen = iid in seen
            print(f"  published={it['published']!r}  recent_enough={recent}  "
                  f"already_seen={already_seen}  title={it['title'][:90]!r}")
        print()


if __name__ == "__main__":
    probe()
