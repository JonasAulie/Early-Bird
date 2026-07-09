"""One-off diagnostic: why didn't the Baker Hughes / Kodiak Gas Services
press release show up in an Early Bird run? Runs the real fetch_ir logic
against the Baker Hughes IR URL and prints every candidate headline it finds
(with extracted date), plus tries a couple of alternate URL patterns in case
/company/news is the wrong index page.

Run via a throwaway workflow_dispatch job on a runner with real network
access (see README's 'known unresolved' section for the pattern).
"""
import requests
from bs4 import BeautifulSoup

from src.fetch_ir import HEADERS, TIMEOUT, _discover_feed, _scrape_listing

CANDIDATES = [
    "https://www.bakerhughes.com/company/news",
    "https://www.bakerhughes.com/press-release",
    "https://www.bakerhughes.com/press-releases",
    "https://www.bakerhughes.com/company/news/press-releases",
    "https://www.bakerhughes.com/investors/news",
]


def probe(url):
    print(f"\n=== {url} ===")
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return
    print(f"  status={resp.status_code}  final_url={resp.url}  len={len(resp.text)}")
    if resp.status_code != 200:
        return

    feed = _discover_feed(url, resp.text)
    print(f"  discovered feed: {feed}")

    items = _scrape_listing(url, resp.text, "bakerhughes")
    print(f"  scrape fallback found {len(items)} candidate headlines:")
    for it in items:
        print(f"    - published={it['published']!r}  title={it['title'][:90]!r}")

    # Also raw-search the page text for 'Kodiak' to see whether the release
    # is even present in the fetched HTML (vs. loaded client-side via JS).
    soup = BeautifulSoup(resp.text, "html.parser")
    hit = "kodiak" in soup.get_text(" ", strip=True).lower()
    print(f"  raw HTML contains 'Kodiak': {hit}")


if __name__ == "__main__":
    for url in CANDIDATES:
        probe(url)
