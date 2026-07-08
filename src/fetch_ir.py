"""Generic fetcher for company investor-relations / newsroom pages that
are not on Oslo Bors Newsweb. Tries, in order:

  1. RSS/Atom feed autodiscovery from the IR page's <link rel="alternate">.
  2. A few common feed URL guesses (page + '/rss', '/feed', etc.)
  3. A best-effort HTML scrape of the news listing page for headline links.

UNVERIFIED: written without network access (see README). Expect to need
per-company tuning once real requests can be made -- some IR sites are
JS-rendered and won't yield anything from a plain requests.get(); those
will show up as empty results and should be logged for follow-up rather
than silently trusted.
"""
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

TIMEOUT = 15
HEADERS = {"User-Agent": "early-bird-bot/1.0 (+contact: jonasaulie@gmail.com)"}

COMMON_FEED_SUFFIXES = ["/rss", "/feed", "/rss.xml", "/feed.xml", "?format=rss"]


def fetch_company_news(company_id: str, ir_url: str) -> List[Dict]:
    if not ir_url:
        return []

    try:
        resp = requests.get(ir_url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[fetch_ir] WARNING: could not load {ir_url} for {company_id}: {e}")
        return []

    feed_url = _discover_feed(ir_url, resp.text)
    if feed_url:
        items = _parse_feed(feed_url, company_id)
        if items:
            return items

    # Fall back to scraping the listing page itself.
    return _scrape_listing(ir_url, resp.text, company_id)


def _discover_feed(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel="alternate", type=lambda t: t and "rss" in t or t and "atom" in t)
    if link and link.get("href"):
        return urljoin(base_url, link["href"])

    for suffix in COMMON_FEED_SUFFIXES:
        candidate = base_url.rstrip("/") + suffix
        try:
            r = requests.head(candidate, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
            if r.status_code == 200:
                return candidate
        except requests.RequestException:
            continue
    return None


def _parse_feed(feed_url: str, company_id: str) -> List[Dict]:
    parsed = feedparser.parse(feed_url)
    out = []
    for entry in parsed.entries[:20]:
        title = entry.get("title")
        link = entry.get("link")
        published = entry.get("published") or entry.get("updated")
        summary = entry.get("summary") or entry.get("description")
        if not title or not link:
            continue
        out.append({
            "title": title,
            "url": link,
            "published": published,
            "summary": summary,
            "source": f"IR feed ({company_id})",
        })
    return out


def _scrape_listing(ir_url: str, html: str, company_id: str) -> List[Dict]:
    """Best-effort, low-confidence fallback: grab anchor tags that look
    like news headlines. No reliable publish-date extraction here, so
    downstream code should treat these as 'needs date verification'.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if not text or len(text) < 15:
            continue
        full_url = urljoin(ir_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        out.append({
            "title": text,
            "url": full_url,
            "published": None,  # unknown -- filter step must be conservative
            "summary": None,
            "source": f"IR page scrape ({company_id})",
        })
        if len(out) >= 15:
            break
    if out:
        print(f"[fetch_ir] NOTE: {company_id} used low-confidence HTML scrape fallback "
              f"(no RSS found, no publish dates) -- verify manually.")
    return out
