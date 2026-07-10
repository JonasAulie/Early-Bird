"""Fallback news source for companies whose own site is blocked by a
network-level WAF/IP-reputation block that no scraping technique from this
environment can get past (confirmed for Saudi Aramco: identical failure --
net::ERR_HTTP2_PROTOCOL_ERROR -- on a plain request, a real headless
browser, AND a third-party reader-proxy service, see
scripts/probe_aramco_subsea7.py and probe_aramco_subsea7_alt_sources.py).

Google News and Bing News RSS run on Google's/Microsoft's own
infrastructure, not the target company's, so a block aimed at the
company's own domain doesn't affect them -- confirmed live to surface real
corporate news (contract awards, project updates) for Aramco that its own
site blocks us from seeing directly.

This is inherently noisier than a company's own press-release feed (mixes
in third-party analyst commentary, opinion pieces, tangential mentions of
the company), so it's used only for companies where the direct path is a
known dead end (see watchlist.json 'news_aggregator_query'), and relies on
the existing relevance filter in draft.py to separate real value-add
stories from aggregator noise -- the same way it already separates signal
from noise in ordinary IR-scrape candidates.
"""
from typing import Dict, List
from urllib.parse import quote

import feedparser
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
TIMEOUT = 20
MAX_ENTRIES_PER_SOURCE = 20


def fetch_news_aggregator(query: str, company_id: str) -> List[Dict]:
    """Returns {title, url, published, summary, source} items from Google
    News + Bing News RSS search for `query`. Best-effort across both
    sources: a failure in one doesn't stop the other, and this never
    raises, so one bad source can't kill the run."""
    out = []
    out.extend(_fetch_google_news_rss(query, company_id))
    out.extend(_fetch_bing_news_rss(query, company_id))
    return out


def _fetch_google_news_rss(query: str, company_id: str) -> List[Dict]:
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[fetch_news_aggregator] WARNING: Google News RSS failed for {company_id}: {e}")
        return []
    parsed = feedparser.parse(resp.text)
    return _entries_to_items(parsed.entries, company_id, "Google News")


def _fetch_bing_news_rss(query: str, company_id: str) -> List[Dict]:
    url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[fetch_news_aggregator] WARNING: Bing News RSS failed for {company_id}: {e}")
        return []
    parsed = feedparser.parse(resp.text)
    return _entries_to_items(parsed.entries, company_id, "Bing News")


def _entries_to_items(entries, company_id: str, source_label: str) -> List[Dict]:
    out = []
    for entry in entries[:MAX_ENTRIES_PER_SOURCE]:
        title = entry.get("title")
        link = entry.get("link")
        if not title or not link:
            continue
        out.append({
            "title": title,
            "url": link,
            "published": entry.get("published"),
            "summary": entry.get("summary"),
            "source": f"{source_label} ({company_id})",
        })
    return out
