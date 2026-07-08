"""One-off diagnostic: verify the new headless-browser fallback in
fetch_ir.py actually rescues Baker Hughes (confirmed JS-only SPA, see
scripts/probe_bakerhughes.py) before trusting it in the full production
scan. Times the fetch so we know the real per-company cost.

The first two live tests: attempt 1 timed out on 'networkidle'; attempt 2
(after switching to domcontentloaded + fixed wait) rendered fine in 6.8s but
the anchor-tag scrape still found 0 headline-shaped links. This version
also dumps raw rendered-DOM diagnostics (anchor count, whether 'Kodiak'
appears anywhere in the rendered text, a sample of anchors) to see what
shape the real markup is in, since our scrape heuristic assumes headlines
sit in plain <a href> tags with >=15 chars of visible text.

Run via a throwaway workflow_dispatch job on a runner with Chromium
installed (playwright install --with-deps chromium).
"""
from bs4 import BeautifulSoup

from src.fetch_ir import HEADERS, HEADLESS_NAV_TIMEOUT_MS, HEADLESS_RENDER_WAIT_MS

URL = "https://www.bakerhughes.com/company/news"


def probe():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(URL, timeout=HEADLESS_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(HEADLESS_RENDER_WAIT_MS)
        html = page.content()
        title = page.title()
        browser.close()

    print(f"page.title() = {title!r}")
    print(f"rendered HTML length = {len(html)}")
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    print(f"rendered text length = {len(text)}")
    print(f"'kodiak' in rendered text: {'kodiak' in text.lower()}")

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    print(f"\ntotal <a href> tags: {len(anchors)}")
    long_text_anchors = [a for a in anchors if len(a.get_text(strip=True)) >= 15]
    print(f"<a href> tags with >=15 chars of text: {len(long_text_anchors)}")
    print("\nfirst 15 anchors (href, text):")
    for a in anchors[:15]:
        print(f"  href={a['href'][:80]!r}  text={a.get_text(strip=True)[:60]!r}")

    print("\nfirst 1500 chars of rendered body text:")
    print(text[:1500])


if __name__ == "__main__":
    probe()
