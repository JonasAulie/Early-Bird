"""One-off diagnostic: why didn't TGS's 'Sells North American Well Data
Products Business to Enverus' Newsweb message (08.07.2026 17:39, messageId
677857) show up as a candidate? Dumps the raw Newsweb API response for
issuer=TGS and runs it through the real fetch_issuer_messages() +
main.is_recent_enough() logic to see exactly where/why it drops out.

Run via a throwaway workflow_dispatch job on a runner with real network
access (see README's 'known unresolved' section for the pattern).
"""
import json
from datetime import datetime, timezone

import requests

from src.fetch_newsweb import API_BASE, HEADERS, TIMEOUT, fetch_issuer_messages
from src.main import lookback_cutoff, is_recent_enough


def probe(issuer: str):
    url = f"{API_BASE}/list?issuer={issuer}"
    print(f"=== raw API response: {url} ===")
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    print(f"status={resp.status_code}")
    payload = resp.json()
    messages = payload.get("data", {}).get("messages", [])
    print(f"{len(messages)} raw messages returned")
    for m in messages[:15]:
        print(f"  id={m.get('messageId')} published={m.get('publishedTime')!r} title={m.get('title', '')[:80]!r}")

    print(f"\n=== through fetch_issuer_messages('{issuer}') ===")
    items = fetch_issuer_messages(issuer)
    print(f"{len(items)} parsed items")

    now = datetime.now(timezone.utc)
    cutoff = lookback_cutoff(now)
    print(f"\n=== recency check (now={now.isoformat()}, cutoff={cutoff.isoformat()}) ===")
    for it in items[:15]:
        recent = is_recent_enough(it["published"], cutoff, now)
        print(f"  recent={recent}  published={it['published']!r}  title={it['title'][:80]!r}")


if __name__ == "__main__":
    probe("TGS")
