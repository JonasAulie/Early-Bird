"""One-off diagnostic: a single Newsweb message (TGS's Enverus divestment,
messageId 677857) showed up as a 'candidate' for five different companies
in the same run -- Kongsberg Maritime, TGS, Solstad Maritime, SED Energy
Holdings, Akastor -- via their respective newsweb_issuer tickers (KOMA, TGS,
SOMAR, SED, AKA). That means the Newsweb API is returning the *same*
response for several issuer codes instead of filtering per-issuer, which
would misattribute real disclosures to the wrong company in a live email.

Dumps the raw API response for every newsweb_issuer ticker in the
watchlist and prints the first message's issuerName from the response
itself (if present) so we can see which tickers are actually being
filtered correctly vs. falling back to some generic/default list.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import json

from src.fetch_newsweb import API_BASE, HEADERS, TIMEOUT
from src.watchlist import load_companies

import requests


def probe():
    companies = load_companies()
    tickers = [(c["id"], c["newsweb_issuer"]) for c in companies if c.get("newsweb_issuer")]
    print(f"{len(tickers)} companies with a newsweb_issuer ticker\n")

    seen_first_msg = {}
    for company_id, ticker in tickers:
        url = f"{API_BASE}/list?issuer={ticker}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            payload = resp.json()
        except Exception as e:
            print(f"{company_id:24s} ticker={ticker:8s} ERROR: {e}")
            continue
        messages = payload.get("data", {}).get("messages", [])
        first = messages[0] if messages else None
        first_issuer_name = first.get("issuerName") if first else None
        first_title = (first.get("title", "")[:60] if first else None)
        first_id = first.get("messageId") if first else None
        print(f"{company_id:24s} ticker={ticker:8s} n={len(messages):3d}  "
              f"first_msg_id={first_id!r:>10}  first_issuerName={first_issuer_name!r}  "
              f"first_title={first_title!r}")
        if first_id:
            seen_first_msg.setdefault(first_id, []).append((company_id, ticker))

    print("\n=== message IDs that appear as the top result for MULTIPLE tickers (mismatch signal) ===")
    for msg_id, owners in seen_first_msg.items():
        if len(owners) > 1:
            print(f"  messageId={msg_id}: {owners}")


if __name__ == "__main__":
    probe()
