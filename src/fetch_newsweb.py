"""Fetches company announcements from Oslo Bors Newsweb for issuers that
are listed there (see watchlist.json 'newsweb_issuer' field).

IMPORTANT / UNVERIFIED: this session had no network access when this file
was written, so the exact Newsweb endpoint/response shape below is a
best-effort guess based on publicly documented Newsweb URL patterns, NOT
a tested integration. Before relying on this in production:

  1. Run `python -c "from src.fetch_newsweb import debug_probe; debug_probe('EQNR')"`
     from an environment with real internet access.
  2. If it 404s or the JSON shape doesn't match, open
     https://newsweb.oslobors.no/ in a browser, open devtools -> Network,
     filter by an issuer, and copy the real request URL + response shape
     here.
"""
from datetime import datetime, timezone
from typing import List, Dict

import requests

CANDIDATE_ENDPOINTS = [
    "https://api2.oslobors.no/newsweb/api/messages?issuer={issuer}",
    "https://newsweb.oslobors.no/api/messages?issuer={issuer}",
]

TIMEOUT = 15


def fetch_issuer_messages(issuer: str) -> List[Dict]:
    """Returns a list of {title, url, published, source} for the given
    Newsweb issuer code. Returns [] (and prints a warning) on any failure
    rather than raising, so one bad company doesn't kill the whole run.
    """
    for endpoint in CANDIDATE_ENDPOINTS:
        url = endpoint.format(issuer=issuer)
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "early-bird-bot/1.0"})
            if resp.status_code != 200:
                continue
            payload = resp.json()
            return _normalize(payload, issuer)
        except (requests.RequestException, ValueError):
            continue
    print(f"[fetch_newsweb] WARNING: could not fetch Newsweb messages for issuer={issuer}")
    return []


def _normalize(payload, issuer: str) -> List[Dict]:
    # Best-effort normalization; adjust once the real response shape is known.
    items = payload.get("messages") or payload.get("data") or payload
    out = []
    if not isinstance(items, list):
        return out
    for item in items:
        title = item.get("title") or item.get("subject")
        msg_id = item.get("id") or item.get("messageId")
        published = item.get("publishedDate") or item.get("published") or item.get("date")
        summary = item.get("body") or item.get("summary") or item.get("attachmentText")
        if not title or not msg_id:
            continue
        out.append({
            "title": title,
            "url": f"https://newsweb.oslobors.no/message/{msg_id}",
            "published": published,
            "summary": summary,
            "source": f"Newsweb ({issuer})",
        })
    return out


def debug_probe(issuer: str):
    """Manual helper to inspect the raw response while verifying the API."""
    for endpoint in CANDIDATE_ENDPOINTS:
        url = endpoint.format(issuer=issuer)
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "early-bird-bot/1.0"})
            print(url, "->", resp.status_code)
            print(resp.text[:1000])
        except requests.RequestException as e:
            print(url, "-> ERROR", e)
