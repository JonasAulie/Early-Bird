"""One-off diagnostic for the final remaining ZERO-item companies from
scripts/probe_watchlist_coverage.py.

v2: Transocean fixed (www.deepwater.com/news/ works, investor.deepwater.com
has server-side issues). SBM Offshore's newsroom page returns 200 with real
content (201KB) via plain requests.get(), but _scrape_listing() still finds
0 headline-shaped anchors -- unlike a bot-block or JS-shell case, this means
the page's real headline markup doesn't match our generic heuristic (plain
<a href> with >=15 chars of visible text). Dump the actual anchor tags found
on the page to see what shape the real headlines are in.

Also checks bakerhughes and chevron again (previously flagged as
inconsistent/intermittent) to see current state.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests
from bs4 import BeautifulSoup

from src.fetch_ir import HEADERS, TIMEOUT, _NAV_JUNK_PATTERNS

URL = "https://www.sbmoffshore.com/newsroom/"


def dump_anchors():
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    print(f"GET {URL} -> {resp.status_code}  len={len(resp.text)}")
    soup = BeautifulSoup(resp.text, "html.parser")
    anchors = soup.find_all("a", href=True)
    print(f"total <a href> tags: {len(anchors)}")

    long_text = [a for a in anchors if len(a.get_text(strip=True)) >= 15]
    print(f"<a href> with >=15 chars text: {len(long_text)}")
    print("\nfirst 20 anchors with >=15 chars text (before junk filter):")
    for a in long_text[:20]:
        text = a.get_text(strip=True)
        is_junk = any(p in text.lower() for p in _NAV_JUNK_PATTERNS)
        print(f"  junk={is_junk}  href={a['href'][:70]!r}  text={text[:70]!r}")

    print("\nfirst 20 anchors total (incl. short text) to see real headline shape:")
    for a in anchors[:20]:
        text = a.get_text(strip=True)
        print(f"  len={len(text):3d}  href={a['href'][:70]!r}  text={text[:70]!r}")

    # Maybe headlines live in a heading tag *inside* the anchor, or the
    # anchor wraps an image with no text and the heading is a sibling --
    # check for h1-h4 tags near article-like containers.
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    print(f"\ntotal heading tags (h1-h4): {len(headings)}")
    for h in headings[:15]:
        print(f"  <{h.name}> text={h.get_text(strip=True)[:70]!r}")


if __name__ == "__main__":
    dump_anchors()
