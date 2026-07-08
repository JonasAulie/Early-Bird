"""Generic fetcher for company investor-relations / newsroom pages that
are not on Oslo Bors Newsweb. Tries, in order:

  1. RSS/Atom feed autodiscovery from the IR page's <link rel="alternate">.
  2. A few common feed URL guesses (page + '/rss', '/feed', etc.)
  3. A best-effort HTML scrape of the news listing page for headline links.
  4. A headless-browser render, only if 1-3 all found nothing -- some IR
     sites (confirmed: Baker Hughes) are pure client-side JS apps and a
     plain requests.get() only ever sees an empty page shell, no matter the
     URL. See scripts/probe_bakerhughes.py for the confirming investigation.
"""
import re
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

TIMEOUT = 15
# A self-identifying UA got blocked by several corporate WAFs (Akamai etc.)
# in live testing; a realistic browser UA gets past most of them (verified
# via scripts/probe_urls.py -- see README's "known unresolved" list for the
# handful that still block bots regardless of UA, e.g. Weatherford).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
}

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
    items = _scrape_listing(ir_url, resp.text, company_id)
    if items:
        return items

    # Both the feed and the plain-HTML scrape found nothing -- likely a
    # client-side-rendered SPA (a plain GET only sees the app shell). Try
    # again with a real browser before giving up on this company entirely.
    return _fetch_via_headless_browser(ir_url, company_id)


def _discover_feed(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel="alternate", type=lambda t: t and "rss" in t or t and "atom" in t)
    if link and link.get("href"):
        return urljoin(base_url, link["href"])

    for suffix in COMMON_FEED_SUFFIXES:
        candidate = base_url.rstrip("/") + suffix
        try:
            r = requests.head(candidate, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
            # Some JS single-page apps 200 on *any* path (client-side router
            # catch-all) and would otherwise look like a valid feed here even
            # though the body is just the app shell -- require a content-type
            # that actually looks like a feed.
            content_type = r.headers.get("content-type", "").lower()
            if r.status_code == 200 and ("xml" in content_type or "rss" in content_type):
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


# Generic nav/footer link text that shows up on every corporate page and is
# never itself a news headline -- filtering these out before they reach the
# LLM cuts noise (and token cost) substantially.
_NAV_JUNK_PATTERNS = (
    "cookie", "privacy", "terms of", "sitemap", "contact us", "log in",
    "sign in", "sign up", "subscribe", "careers", "job openings",
    "read more", "learn more", "view all", "see all", "back to",
    "skip to", "accept all", "manage preferences", "follow us",
)


# Norwegian month names dateutil doesn't understand -> English, so a date
# like "8. juli 2026" on a Norwegian IR page still parses.
_NO_TO_EN_MONTH = {
    "januar": "january", "februar": "february", "mars": "march",
    "mai": "may", "juni": "june", "juli": "july",
    "oktober": "october", "desember": "december",
    # april/august/september/november are close enough for dateutil already.
}

_MONTH_ALT = (
    "januar|februar|mars|mai|juni|juli|oktober|desember"
    "|january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)

# A plausible date substring sitting next to a headline. Kept deliberately
# narrow so we only ever hand dateutil a real date fragment (fuzzy parsing a
# whole headline would happily turn "Q3 2026" or a rig count into a date).
_DATE_HINT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"                                      # 2026-07-08
    r"|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"                     # 08.07.2026 / 8-7-26
    rf"|\d{{1,2}}\.?\s+(?:{_MONTH_ALT})\.?\s+\d{{4}}"         # 8 July 2026 / 8. juli 2026
    rf"|(?:{_MONTH_ALT})\.?\s+\d{{1,2}},?\s+\d{{4}}",         # July 8, 2026
    re.IGNORECASE,
)

# A date baked into the article URL itself, e.g. /news/2026/07/08/title.
_HREF_DATE_RE = re.compile(r"(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})")

# Machine-readable date attributes many CMSs emit next to a headline, e.g.
# <time datetime="2026-07-08T09:00:00Z">8 Jul</time>. get_text() throws these
# away, so we check the attributes directly -- rescues pages whose visible date
# is relative ("2 days ago") or rendered by JS but whose markup still carries a
# real timestamp.
_DATE_ATTRS = ("datetime", "data-date", "data-datetime", "data-published", "data-time")


def _parse_iso_attr(val: str):
    if not val or not re.search(r"20\d\d", val):
        return None
    try:
        dt = dateparser.parse(val)
        return dt.isoformat() if dt else None
    except (ValueError, OverflowError, TypeError):
        return None


def _attr_date_in(node):
    """First machine-readable date attribute found within a scope node."""
    if not hasattr(node, "find_all"):
        return None
    candidates = [node] if getattr(node, "attrs", None) else []
    candidates += node.find_all(True)
    for el in candidates:
        for attr in _DATE_ATTRS:
            parsed = _parse_iso_attr(el.get(attr))
            if parsed:
                return parsed
    return None


def _parse_date_string(raw: str):
    low = raw.lower()
    for no, en in _NO_TO_EN_MONTH.items():
        if no in low:
            low = low.replace(no, en)
    # Ambiguous all-numeric dates need a locale guess, since dayfirst only
    # matters when both the day and month are plain numbers (a named month,
    # e.g. "July 8, 2026", parses correctly either way). ISO (year-first,
    # dashes) is unambiguous. Slash-separated numeric dates (7/8/2026) are
    # the US convention (month-first) -- almost every US IR page (Baker
    # Hughes, Chevron, Patterson-UTI, etc.) uses this, whereas dot-separated
    # (08.07.2026) is the European/Norwegian convention (day-first). Getting
    # this backwards silently swaps day and month for any date past the 12th.
    if re.match(r"\s*\d{4}-\d{1,2}-\d{1,2}", low):
        dayfirst = False
    elif "/" in low:
        dayfirst = False
    else:
        dayfirst = True
    try:
        dt = dateparser.parse(low, dayfirst=dayfirst, fuzzy=True)
        return dt.isoformat() if dt else None
    except (ValueError, OverflowError):
        return None


def _extract_published(anchor, href: str):
    """Best-effort publish date for a scraped headline. Tries a date in the
    article URL first (most reliable, language-neutral), then a date string
    in the headline's own/parent/grandparent container. Returns an ISO string
    or None -- and None means the recency filter drops it, so we never resurface
    an undated stale headline."""
    m = _HREF_DATE_RE.search(href or "")
    if m:
        y, mo, d = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    node = anchor
    for _ in range(3):  # headline scope, then widen to its card / row
        if node is None:
            break
        attr_date = _attr_date_in(node)
        if attr_date:
            return attr_date
        hint = _DATE_HINT_RE.search(node.get_text(" ", strip=True))
        if hint:
            parsed = _parse_date_string(hint.group(0))
            if parsed:
                return parsed
        node = node.parent
    return None


def _scrape_listing(ir_url: str, html: str, company_id: str) -> List[Dict]:
    """Best-effort fallback for pages with no RSS feed: grab anchor tags that
    look like news headlines and try to pin a publish date on each (see
    _extract_published). Undated ones are kept here but get dropped by the
    recency filter downstream, so stale headlines never reach the model.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    dated = 0
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if not text or len(text) < 15:
            continue
        if any(p in text.lower() for p in _NAV_JUNK_PATTERNS):
            continue
        full_url = urljoin(ir_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        published = _extract_published(a, href)
        if published:
            dated += 1
        out.append({
            "title": text,
            "url": full_url,
            "published": published,
            "summary": None,
            "source": f"IR page scrape ({company_id})",
        })
        if len(out) >= 15:
            break
    if out:
        print(f"[fetch_ir] NOTE: {company_id} used HTML scrape fallback "
              f"({dated}/{len(out)} headlines had an extractable date; undated ones "
              f"are dropped by the recency filter).")
    return out


HEADLESS_NAV_TIMEOUT_MS = 15000
HEADLESS_RENDER_WAIT_MS = 5000
HEADLESS_EXTRA_WAIT_MS = 4000  # one retry wait if the first render looks empty
HEADLESS_MAX_ATTEMPTS = 2


def _fetch_via_headless_browser(ir_url: str, company_id: str) -> List[Dict]:
    """Last-resort fallback for IR pages that are pure client-side apps (a
    plain requests.get() only ever sees an empty shell -- confirmed for
    Baker Hughes via scripts/probe_bakerhughes.py). Renders the page with a
    real (headless) Chromium and re-runs the same anchor-tag scrape against
    the resulting DOM. Only reached when the feed + plain-HTML paths both
    found nothing, so this shouldn't run for the majority of companies.

    Live testing showed the fixed render-wait is occasionally too short --
    same code, same URL, one run got 0 anchors and the next got 510 -- so
    this retries once with extra wait time before giving up, rather than
    trusting a single roll of real-world network timing.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"[fetch_ir] WARNING: playwright not installed, skipping headless fallback for {company_id}")
        return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                # "networkidle" times out on modern SPAs that never go fully
                # quiet (analytics beacons, polling, chat widgets, etc, keep
                # firing indefinitely) even once the actual content is
                # rendered. Wait for the DOM instead, then give React/Vue/etc
                # a fixed window to hydrate and paint the news list.
                page.goto(ir_url, timeout=HEADLESS_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(HEADLESS_RENDER_WAIT_MS)
                items = _scrape_listing(ir_url, page.content(), company_id)
                attempt = 1
                while not items and attempt < HEADLESS_MAX_ATTEMPTS:
                    attempt += 1
                    page.wait_for_timeout(HEADLESS_EXTRA_WAIT_MS)
                    items = _scrape_listing(ir_url, page.content(), company_id)
            finally:
                browser.close()
    except Exception as e:
        print(f"[fetch_ir] WARNING: headless browser fetch failed for {company_id} ({ir_url}): {e}")
        return []

    if items:
        print(f"[fetch_ir] NOTE: {company_id} needed the headless-browser fallback "
              f"(plain HTTP got an empty JS app shell) -- found {len(items)} headlines "
              f"(attempt {attempt}/{HEADLESS_MAX_ATTEMPTS}).")
    else:
        print(f"[fetch_ir] NOTE: {company_id} headless-browser fallback rendered the page "
              f"but still found no headline-shaped links after {HEADLESS_MAX_ATTEMPTS} attempts "
              f"-- may need per-site tuning.")
    return items
