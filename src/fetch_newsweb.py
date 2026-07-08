"""Fetches company announcements from Oslo Bors Newsweb for issuers that
are listed there (see watchlist.json 'newsweb_issuer' field).

Newsweb (newsweb.oslobors.no) is a React SPA that fetches its own runtime
config from /urls.json, which points the frontend at the real backend --
this overrides the build-time REACT_APP_API_URL baked into the JS bundle
(which is a dead/internal dev host and not usable). Confirmed via a
Playwright network trace (see scripts/probe_newsweb_playwright.py):

    GET https://newsweb.oslobors.no/urls.json
    -> {"api_large": "https://api3.oslo.oslobors.no", ...}

    GET https://api3.oslo.oslobors.no/v1/newsreader/list?issuer=EQNR
    -> {"data": {"messages": [{"messageId": 677726, "title": "...",
                                "publishedTime": "2026-07-07T06:00:05.862Z",
                                "issuerName": "Equinor ASA", ...}, ...]}}
"""
from typing import List, Dict

import requests

API_BASE = "https://api3.oslo.oslobors.no/v1/newsreader"
TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_issuer_messages(issuer: str) -> List[Dict]:
    """Returns a list of {title, url, published, summary, source} for the
    given Newsweb issuer code. Returns [] (and prints a warning) on any
    failure rather than raising, so one bad company doesn't kill the run.
    """
    url = f"{API_BASE}/list?issuer={issuer}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[fetch_newsweb] WARNING: could not fetch Newsweb messages for issuer={issuer}: {e}")
        return []

    messages = payload.get("data", {}).get("messages", [])
    out = []
    for item in messages:
        title = item.get("title")
        message_id = item.get("messageId")
        published = item.get("publishedTime")
        if not title or not message_id:
            continue
        categories = item.get("category") or []
        category_text = ", ".join(c.get("category_en", "") for c in categories if c.get("category_en"))
        out.append({
            "title": title,
            "url": f"https://newsweb.oslobors.no/message/{message_id}",
            "published": published,
            "summary": category_text or None,
            "source": f"Newsweb ({issuer})",
        })
    return out


def debug_probe(issuer: str):
    """Manual helper to inspect the raw response while verifying the API."""
    url = f"{API_BASE}/list?issuer={issuer}"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    print(url, "->", resp.status_code)
    print(resp.text[:2000])
