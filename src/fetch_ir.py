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
from zoneinfo import ZoneInfo

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
        # Don't give up here -- a WAF/Akamai-style block (403 Forbidden) on a
        # plain requests.get() is exactly the kind of thing a real headless
        # browser can get past (real TLS/JS fingerprint, not just a spoofed
        # User-Agent header). Confirmed needed for Weatherford/Chevron/BP/
        # Orsted. Fall through to the same headless path used for JS-only
        # SPAs instead of returning [] immediately.
        print(f"[fetch_ir] WARNING: could not load {ir_url} for {company_id} via plain HTTP "
              f"({e}) -- trying headless browser before giving up.")
        return _fetch_via_headless_browser(ir_url, company_id)

    feed_url = _discover_feed(ir_url, resp.text)
    if feed_url:
        items = _parse_feed(feed_url, company_id)
        if items:
            return items

    # Fall back to scraping the listing page itself.
    items = _scrape_listing(ir_url, resp.text, company_id)
    if items and any(it.get("published") for it in items):
        return items

    # Either the feed/plain-HTML scrape found nothing at all (likely a
    # client-side-rendered SPA, a plain GET only sees the app shell), or it
    # found anchors but none with an extractable date -- e.g. Baker Hughes'
    # investor-platform page 200s on a plain GET but the real dated headline
    # list is populated by JS after load, so a plain scrape only picks up
    # undated nav links. Either way, try a real browser before giving up.
    headless_items = _fetch_via_headless_browser(ir_url, company_id)
    return headless_items or items


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

# A time-of-day immediately trailing a date hint, e.g. Equinor's IR listing
# renders headlines as "10 July 2026|08:00 (CEST)Equinor's second quarter...",
# and Eni's as "13 July 2026 - 1:00 PM CESTEni and BMW Group...". Without
# this, _extract_published only ever captured the date and dateutil
# defaulted the missing time to midnight -- which then hit the date-only
# "whole day counts" fallback in main.py's recency filter and let an item
# genuinely published shortly before the real 08:30 Oslo cutoff slip in as
# if it were still within the prior day's window (confirmed live for
# Equinor's "|08:00" case; a second real format, Eni's " - 1:00 PM", was
# separately confirmed to fall through this same regex before this fix --
# it happened not to matter that time since 1pm is well after any cutoff,
# but a morning item in that format would have hit the exact same bug).
# Timezone abbreviation matched against an explicit list, not a generic
# \w{2,5} -- the source text runs straight into the headline with no
# separator ("...CESTEni and BMW..."), and a generic greedy quantifier
# silently over-matched into "CESTE" (swallowing the headline's first
# letter), which no longer matched anything recognizable and quietly
# dropped the timezone localization instead of just failing loudly.
_TZ_ABBR = r"CEST|CET|GMT|UTC|BST|EST|EDT|CST|CDT|MST|MDT|PST|PDT"
_TIME_HINT_RE = re.compile(
    rf"\s*[-|]?\s*(\d{{1,2}}:\d{{2}})\s*([AaPp]\.?[Mm]\.?)?\s*\(?\s*({_TZ_ABBR})?\s*\)?",
    re.IGNORECASE,
)

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
        if dt and dt.tzinfo is None and re.search(r"\bcest\b|\bcet\b", low):
            # dateutil doesn't resolve "CEST"/"CET" to an offset on its own
            # (fuzzy mode just ignores the token) -- but both names mean
            # Europe/Oslo's own zone, so attach it explicitly rather than
            # leave the timestamp wrongly implied to be UTC.
            dt = dt.replace(tzinfo=ZoneInfo("Europe/Oslo"))
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
        if node is not anchor:
            # Stop widening the moment the scope contains more than this
            # one headline's own link -- a wider ancestor that wraps
            # multiple cards/rows (common on listing pages once you climb
            # past the single-item card) would otherwise attribute a
            # *different* item's date to this headline. Confirmed live: an
            # old Baker Hughes press release (Twenty20 Energy gas turbine
            # order, actually published 11 February) slipped through the
            # recency filter this way, apparently having inherited a
            # sibling headline's fresher date from a shared ancestor.
            other_links = [a for a in node.find_all("a", href=True) if a is not anchor]
            if other_links:
                break
        attr_date = _attr_date_in(node)
        if attr_date:
            return attr_date
        text = node.get_text(" ", strip=True)
        hint = _DATE_HINT_RE.search(text)
        if hint:
            date_str = hint.group(0)
            # Check for a time-of-day (and optional tz abbreviation) sitting
            # right after the date, e.g. "10 July 2026|08:00 (CEST)" -- see
            # _TIME_HINT_RE for why this matters for the recency cutoff.
            time_hint = _TIME_HINT_RE.match(text[hint.end():hint.end() + 20])
            if time_hint:
                date_str = f"{date_str} {time_hint.group(0).strip(' |-')}"
            parsed = _parse_date_string(date_str)
            if parsed:
                return parsed
        node = node.parent
    return None


_SCRAPE_OUTPUT_CAP = 20


def _scrape_listing(ir_url: str, html: str, company_id: str) -> List[Dict]:
    """Best-effort fallback for pages with no RSS feed: grab anchor tags that
    look like news headlines and try to pin a publish date on each (see
    _extract_published). Undated ones are kept here but get dropped by the
    recency filter downstream, so stale headlines never reach the model.

    Scans every matching anchor on the page (no early break) and sorts dated
    candidates first before capping the output -- on many real IR pages
    (confirmed for Baker Hughes' investor-platform page) the nav menu's
    undated links appear before the actual headline links in the DOM, so
    breaking at the first N matches was silently starving every real,
    dated headline out of the result.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
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
        candidates.append({
            "title": text,
            "url": full_url,
            "published": published,
            "summary": None,
            "source": f"IR page scrape ({company_id})",
        })

    # Dated candidates first (real headlines), undated ones after (mostly nav
    # links) -- stable sort preserves each group's original DOM order.
    candidates.sort(key=lambda it: it["published"] is None)
    out = candidates[:_SCRAPE_OUTPUT_CAP]
    dated = sum(1 for it in out if it["published"])
    if out:
        print(f"[fetch_ir] NOTE: {company_id} used HTML scrape fallback "
              f"({dated}/{len(out)} headlines had an extractable date; undated ones "
              f"are dropped by the recency filter).")
    return out


HEADLESS_NAV_TIMEOUT_MS = 20000
# A bare SPA app shell has only a handful of nav/footer anchors; once the news
# list actually renders the anchor count jumps into the dozens/hundreds. Poll
# for that instead of trusting a fixed sleep (which was flaky -- same URL got
# 0 anchors one run and 500+ the next). This is a best-effort accelerator, not
# a hard gate: if it never crosses the threshold we still scrape whatever did
# render once the poll window elapses.
HEADLESS_CONTENT_ANCHOR_THRESHOLD = 40
HEADLESS_CONTENT_TIMEOUT_MS = 15000
HEADLESS_SETTLE_WAIT_MS = 1500


def _render_page_headless(url: str, label: str) -> str:
    """Renders a page with a real (headless) Chromium and returns the fully
    loaded HTML, or None on failure. Shared by the listing-page fallback and
    fetch_article_body() below -- both need "wait for JS to actually
    populate the page" logic, just applied to different content.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"[fetch_ir] WARNING: playwright not installed, skipping headless fallback for {label}")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                # "networkidle" times out on modern SPAs that never go fully
                # quiet (analytics beacons, polling, chat widgets keep firing
                # forever) even once the content is painted. Wait for the DOM,
                # then poll until the news list has actually populated (anchor
                # count crosses the threshold) rather than guessing a sleep.
                page.goto(url, timeout=HEADLESS_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                try:
                    page.wait_for_function(
                        "n => document.querySelectorAll('a').length > n",
                        arg=HEADLESS_CONTENT_ANCHOR_THRESHOLD,
                        timeout=HEADLESS_CONTENT_TIMEOUT_MS,
                    )
                except Exception:
                    # Never crossed the threshold in time -- fall through and
                    # scrape whatever rendered anyway (some real pages are small).
                    pass
                page.wait_for_timeout(HEADLESS_SETTLE_WAIT_MS)
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        print(f"[fetch_ir] WARNING: headless browser fetch failed for {label} ({url}): {e}")
        return None


def _fetch_via_headless_browser(ir_url: str, company_id: str) -> List[Dict]:
    """Last-resort fallback for IR pages that are pure client-side apps (a
    plain requests.get() only ever sees an empty shell -- confirmed for
    Baker Hughes via scripts/probe_bakerhughes.py). Renders the page with a
    real (headless) Chromium and re-runs the same anchor-tag scrape against
    the resulting DOM. Only reached when the feed + plain-HTML paths both
    found nothing, so this shouldn't run for the majority of companies.
    """
    html = _render_page_headless(ir_url, company_id)
    if not html:
        return []

    items = _scrape_listing(ir_url, html, company_id)
    if items:
        print(f"[fetch_ir] NOTE: {company_id} needed the headless-browser fallback "
              f"(plain HTTP got an empty JS app shell) -- found {len(items)} headlines.")
    else:
        print(f"[fetch_ir] NOTE: {company_id} headless-browser fallback rendered the page "
              f"but still found no headline-shaped links -- may need per-site tuning.")
    return items


_ARTICLE_BODY_MAX_CHARS = 4000


def fetch_article_body(url: str, label: str = "") -> str:
    """Fetches the full text of a single article/press-release page.

    IR-scrape candidates only ever carry the anchor's headline text (see
    _scrape_listing -- summary is always None), which forces the drafter to
    write a one-line comment even for a story with real substance. This is
    called only for the small number of candidates that survive the
    recency filter (a handful per run, not the ~20-headline listing
    scrape), so a slower per-page fetch here is an acceptable tradeoff for
    giving the model enough grounding to write a proper multi-sentence
    comment instead of a bare-headline placeholder.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        text = _extract_article_text(resp.text)
        if text and len(text) > 200:
            return text
    except requests.RequestException:
        pass

    # Plain request failed, or returned too little (or nothing but a cookie
    # banner -- see _extract_article_text) to be the real article body --
    # try headless as a last resort, mirroring the WAF/SPA fallback used for
    # the listing scrape.
    html = _render_page_headless(url, label or url)
    if html:
        text = _extract_article_text(html)
        if text:
            return text
    return None


# Cookie-consent banners are near-universal on corporate IR sites and often
# aren't tagged with any "nav"/"footer"/"cookie" class our decompose list
# would catch -- confirmed for Baker Hughes' investor-platform page, where
# the banner was the single largest <p> on the page and got returned as the
# "article body" for a Sabine Pass LNG contract announcement. Filter any
# element whose own class/id names it as consent/legal chrome, and as a
# content-level backstop (in case a page hides the banner in an unlabeled
# div), reject the whole extraction if what's left still reads like one.
_CONSENT_CLASS_KEYWORDS = ("cookie", "consent", "gdpr", "onetrust", "cc-window", "cc-banner")
_COOKIE_BANNER_PHRASES = (
    "cookie settings", "cookie notice", "cookie policy", "we use cookies",
    "storing of active cookies", "reject all non-essential cookies",
)


def _extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    # find_all() materializes the full match list up front, but consent SDKs
    # commonly nest several class/id-carrying elements inside each other
    # (e.g. OneTrust's #onetrust-consent-sdk wrapping #onetrust-banner-sdk) --
    # decomposing an ancestor also destroys descendants already in that same
    # list, so a later iteration can hit an already-decomposed tag (its
    # .attrs is cleared to None, so .get() raises). Skip anything already
    # decomposed rather than crash on it.
    for tag in soup.find_all(attrs={"class": True}):
        if getattr(tag, "decomposed", False):
            continue
        classes = " ".join(tag.get("class", [])).lower()
        if any(kw in classes for kw in _CONSENT_CLASS_KEYWORDS):
            tag.decompose()
    for tag in soup.find_all(attrs={"id": True}):
        if getattr(tag, "decomposed", False):
            continue
        if any(kw in tag.get("id", "").lower() for kw in _CONSENT_CLASS_KEYWORDS):
            tag.decompose()

    # Prefer a semantic <article> tag or a common CMS "content" container if
    # present -- keeps nav/footer boilerplate out of the extracted text on
    # pages where those elements aren't cleanly tagged as nav/footer.
    container = soup.find("article")
    if not container:
        container = soup.find(attrs={"class": lambda c: c and "content" in " ".join(c).lower()})
    paragraphs = (container or soup).find_all("p")
    text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
    text = " ".join(text.split())
    if not text:
        return None
    lowered = text.lower()
    if any(phrase in lowered for phrase in _COOKIE_BANNER_PHRASES):
        return None
    return text[:_ARTICLE_BODY_MAX_CHARS]
