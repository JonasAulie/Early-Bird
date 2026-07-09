"""One-off diagnostic: EQNR and NORAM both returned 0 messages from
.../v1/newsreader/list?issuer=X just now, despite both having published
today (confirmed via Jonas's real Early Bird issue). That suggests the
list endpoint is a small rolling window, not 'everything from today' --
messages can roll off it before we ever fetch them. Dump the FULL raw JSON
(not just the messages array) to look for pagination/count metadata, and
try common extra query params (limit, count, page, from/to dates) to see
if a fuller/paginated list is available.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import json

import requests

from src.fetch_newsweb import API_BASE, HEADERS, TIMEOUT

ISSUER = "EQNR"

CANDIDATES = [
    f"{API_BASE}/list?issuer={ISSUER}",
    f"{API_BASE}/list?issuer={ISSUER}&limit=50",
    f"{API_BASE}/list?issuer={ISSUER}&count=50",
    f"{API_BASE}/list?issuer={ISSUER}&pageSize=50",
    f"{API_BASE}/list?issuer={ISSUER}&days=7",
    f"{API_BASE}/list?issuer={ISSUER}&fromDate=2026-07-01&toDate=2026-07-09",
    f"{API_BASE}/list?issuer={ISSUER}&page=1&size=50",
]


def probe():
    for url in CANDIDATES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            payload = resp.json()
        except Exception as e:
            print(f"=== {url} -> ERROR: {e} ===\n")
            continue
        messages = payload.get("data", {}).get("messages", [])
        # Print everything except the messages array itself, to spot
        # pagination/count metadata without a huge dump.
        data_keys = list(payload.get("data", {}).keys())
        header = payload.get("header", {})
        print(f"=== {url} -> {resp.status_code} ===")
        print(f"  data keys: {data_keys}   header: {header}")
        print(f"  {len(messages)} messages")
        for m in messages[:3]:
            print(f"    id={m.get('messageId')} published={m.get('publishedTime')!r} "
                  f"title={m.get('title', '')[:60]!r}")
        print()


if __name__ == "__main__":
    probe()
