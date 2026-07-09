"""Deeper diagnostic for the last 2 unresolved companies: Saudi Aramco and
Subsea7. Earlier probing found: Aramco times out on plain requests.get() for
every URL tried; Subsea7 returns an identical tiny (~1938 byte) page for
every URL tried. Neither of those symptoms was investigated with a headless
browser or by dumping the raw response body -- do that here to find out
what's actually happening (cookie-consent wall? geo-block? redirect chain?
JS-only SPA that a longer timeout or a real browser fingerprint gets past?).

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests

from src.fetch_ir import HEADERS, _scrape_listing, _fetch_via_headless_browser

ARAMCO_URLS = [
    "https://www.aramco.com/en/news-media",
    "https://www.aramco.com/en/news-media/news",
    "https://www.aramco.com/en/investors",
    "https://www.aramco.com/en/investors/investor-news",
]

SUBSEA7_URLS = [
    "https://subsea7.com/en/media/news.html",
    "https://subsea7.com/en/media.html",
    "https://subsea7.com/en/newsroom.html",
    "https://subsea7.com/",
]


def dump_plain(label, url, timeout):
    print(f"--- {label}: plain requests.get({url}, timeout={timeout}) ---")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        print(f"  status={resp.status_code} final_url={resp.url} len={len(resp.text)}")
        print(f"  history={[r.status_code for r in resp.history]} redirects_to={[r.headers.get('location') for r in resp.history]}")
        body = resp.text
        print(f"  first 500 chars:\n{body[:500]!r}")
        if resp.status_code == 200:
            items = _scrape_listing(resp.url, body, label)
            dated = sum(1 for it in items if it.get("published"))
            print(f"  scrape_listing: {len(items)} candidates, {dated} dated")
    except requests.RequestException as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()


def dump_headless(label, url):
    print(f"--- {label}: headless browser render({url}) ---")
    try:
        items = _fetch_via_headless_browser(url, label)
        dated = sum(1 for it in items if it.get("published"))
        print(f"  headless scrape: {len(items)} candidates, {dated} dated")
        for it in items[:8]:
            print(f"    published={it['published']!r}  title={it['title'][:70]!r}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()


if __name__ == "__main__":
    print("=" * 30, "SAUDI ARAMCO", "=" * 30)
    for url in ARAMCO_URLS:
        dump_plain("aramco", url, timeout=30)
    dump_headless("aramco", ARAMCO_URLS[0])

    print("=" * 30, "SUBSEA7", "=" * 30)
    for url in SUBSEA7_URLS:
        dump_plain("subsea7", url, timeout=15)
    dump_headless("subsea7", SUBSEA7_URLS[0])
