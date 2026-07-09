"""One-off diagnostic for SBM Offshore: plain requests.get() only returns
nav-menu markup (1 heading tag total, no headline links) -- the newsroom
list is client-side rendered. But our headless fallback (up to ~36s worst
case: 20s nav timeout + 15s anchor-count poll + 1.5s settle) still found 0
anchors past the threshold. This renders the page with a longer, unbounded
wait and dumps what actually shows up, to see if the news list ever
populates or if something else (e.g. a cookie-consent overlay blocking
rendering, or an infinite-scroll/lazy-load pattern) is going on.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.fetch_ir import HEADERS

URL = "https://www.sbmoffshore.com/newsroom/"


def probe():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(URL, timeout=25000, wait_until="domcontentloaded")

        # Generous wait, checking anchor count at each step to see the
        # actual render timeline instead of guessing one fixed value.
        for wait_s in (2, 5, 10, 15):
            page.wait_for_timeout(wait_s * 1000)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            anchors = soup.find_all("a", href=True)
            headings = soup.find_all(["h1", "h2", "h3", "h4"])
            print(f"after +{wait_s}s: {len(anchors)} anchors, {len(headings)} headings, "
                  f"html_len={len(html)}")

        title = page.title()
        print(f"\nfinal page title: {title!r}")

        # Dump final anchor list to see the real shape once rendered.
        final_html = page.content()
        soup = BeautifulSoup(final_html, "html.parser")
        anchors = soup.find_all("a", href=True)
        print(f"\nfinal anchor count: {len(anchors)}")
        for a in anchors[:40]:
            text = a.get_text(strip=True)
            if len(text) >= 10:
                print(f"  len={len(text):3d}  href={a['href'][:70]!r}  text={text[:70]!r}")

        # Check for common cookie-consent / overlay blockers.
        text_all = soup.get_text(" ", strip=True).lower()
        for signal in ("accept cookies", "cookie consent", "we use cookies", "manage preferences"):
            if signal in text_all:
                print(f"\nPossible cookie/consent overlay signal found: {signal!r}")

        browser.close()


if __name__ == "__main__":
    probe()
