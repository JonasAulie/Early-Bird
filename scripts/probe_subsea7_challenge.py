"""Subsea7 serves a JS bot-challenge page ("Challenge Validation", a
cp_clge_done() reload callback -- looks like a PerimeterX/Akamai-style
client-side challenge) on every URL, identical across paths. Test whether
a real headless browser just needs more time for the challenge JS to
resolve and reload into the real page, or whether it's blocked outright
(e.g. via navigator.webdriver detection). Poll page title/content over an
extended wait instead of a single fixed timeout.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import time

from playwright.sync_api import sync_playwright

from src.fetch_ir import HEADERS, _scrape_listing

URL = "https://www.subsea7.com/en/media/news.html"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=HEADERS["User-Agent"])
        page = context.new_page()

        webdriver_flag = page.evaluate("() => navigator.webdriver")
        print(f"navigator.webdriver before goto: {webdriver_flag!r}")

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        for i in range(6):
            time.sleep(5)
            title = page.title()
            url = page.url
            anchors = page.eval_on_selector_all("a", "els => els.length")
            print(f"t={5*(i+1):3d}s  title={title!r}  url={url!r}  anchor_count={anchors}")
            if "challenge" not in title.lower() and anchors > 40:
                print("  -> looks like real content loaded, stopping early")
                break

        webdriver_flag_after = page.evaluate("() => navigator.webdriver")
        print(f"navigator.webdriver after wait: {webdriver_flag_after!r}")

        html = page.content()
        print(f"final HTML length: {len(html)}")
        items = _scrape_listing(URL, html, "subsea7")
        dated = sum(1 for it in items if it.get("published"))
        print(f"scrape_listing: {len(items)} candidates, {dated} dated")
        for it in items[:8]:
            print(f"  published={it['published']!r}  title={it['title'][:70]!r}")

        browser.close()


if __name__ == "__main__":
    main()
