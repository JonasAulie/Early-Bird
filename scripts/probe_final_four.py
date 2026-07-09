"""One-off diagnostic for the last 4 unresolved companies: Baker Hughes,
Saudi Aramco, Chevron, Subsea7.

Key lead: the SBM Offshore fix showed that a company's own nav sometimes
links to the REAL press-release page on a different path/subdomain than
what we're scraping. Baker Hughes' own site nav (captured in an earlier DOM
dump) included a link to investors.bakerhughes.com -- a separate investor-
relations platform subdomain that may be server-rendered (many companies
host IR content on Q4/EQS-style platforms distinct from the marketing site,
which explains why the main bakerhughes.com is a pure SPA but the investor
subdomain might not be). Try that plus a few common IR-platform path
patterns for each of the 4 remaining companies.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests
from bs4 import BeautifulSoup

from src.fetch_ir import HEADERS, TIMEOUT, _scrape_listing

CANDIDATES = {
    "bakerhughes": [
        "https://investors.bakerhughes.com/",
        "https://investors.bakerhughes.com/news",
        "https://investors.bakerhughes.com/news-events/press-releases",
        "https://investors.bakerhughes.com/news-events",
    ],
    "saudiaramco": [
        "https://www.aramco.com/en/investors/investor-news",
        "https://www.aramco.com/en/news-media",
        "https://www.aramco.com/en/news-media/news",
    ],
    "chevron": [
        "https://www.chevron.com/newsroom/archive?contenttype=press%20release",
        "https://www.chevron.com/newsroom",
        "https://www.chevron.com/newsroom/press-releases",
    ],
    "subsea7": [
        "https://subsea7.com/en/media/news.html",
        "https://subsea7.com/en/media.html",
        "https://subsea7.com/en/media/press-releases.html",
    ],
}


def probe(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"  {url} -> {resp.status_code}  final={resp.url}  len={len(resp.text)}")
        if resp.status_code == 200:
            items = _scrape_listing(resp.url, resp.text, "probe")
            dated = sum(1 for it in items if it.get("published"))
            print(f"    scrape_listing found {len(items)} candidates, {dated} dated")
            for it in items[:5]:
                print(f"      published={it['published']!r}  title={it['title'][:70]!r}")
    except requests.RequestException as e:
        print(f"  {url} -> ERROR: {e}")


if __name__ == "__main__":
    for company_id, urls in CANDIDATES.items():
        print(f"=== {company_id} ===")
        for url in urls:
            probe(url)
        print()
