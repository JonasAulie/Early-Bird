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

The list endpoint above only returns the title, not the disclosure body --
using it alone made the drafter's comments generic/wrong (e.g. "no
transaction details were disclosed" on a release that actually specified a
USD 100m+ price and an earn-out). The full text lives at a separate
endpoint (see scripts/probe_newsweb_message_body.py):

    GET https://api3.oslo.oslobors.no/v1/newsreader/message?messageId=677857
    -> {"data": {"message": {"body": "OSLO, Norway (8 July 2026) - ...", ...}}}

IMPORTANT: calling /list?issuer=X with no date range has been observed to
silently return an EMPTY messages array even when the issuer has published
recently (confirmed for EQNR and NORAM via scripts/probe_newsweb_list_size.py
-- messages that were confirmed to exist, e.g. Equinor's Q2 trading update,
were completely missing from the undated call, while the exact same issuer
with an explicit &fromDate=...&toDate=... range returned real data). This
looks like an active bug/instability in the API's own default-range
behaviour, not something we can rely on. We therefore always pass an
explicit date range (see LOOKBACK_DAYS below) rather than trusting the
undated call.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import requests

API_BASE = "https://api3.oslo.oslobors.no/v1/newsreader"
TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}
# Generously wider than main.py's actual recency cutoff (1-3 days) -- the
# recency filter downstream narrows it back down, this just protects against
# ever missing something because the date window itself was too tight.
LOOKBACK_DAYS = 10


def fetch_issuer_messages(issuer: str) -> List[Dict]:
    """Returns a list of {title, url, published, summary, source} for the
    given Newsweb issuer code. Returns [] (and prints a warning) on any
    failure rather than raising, so one bad company doesn't kill the run.
    """
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()
    url = f"{API_BASE}/list?issuer={issuer}&fromDate={from_date}&toDate={to_date}"
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
        body = _fetch_message_body(message_id)
        out.append({
            "title": title,
            "url": f"https://newsweb.oslobors.no/message/{message_id}",
            "published": published,
            # Prefer the full disclosure text over the bare category tag so
            # the drafter has real figures/detail to work from -- fall back
            # to the category if the body fetch fails for some reason.
            "summary": body or category_text or None,
            "source": f"Newsweb ({issuer})",
        })
    return out


def _fetch_message_body(message_id: int):
    url = f"{API_BASE}/message?messageId={message_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[fetch_newsweb] WARNING: could not fetch message body for messageId={message_id}: {e}")
        return None
    body = payload.get("data", {}).get("message", {}).get("body")
    return body.strip() if body else None


def debug_probe(issuer: str):
    """Manual helper to inspect the raw response while verifying the API."""
    url = f"{API_BASE}/list?issuer={issuer}"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    print(url, "->", resp.status_code)
    print(resp.text[:2000])
