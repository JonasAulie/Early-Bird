"""One-off diagnostic: Quartr's public REST API (quartr.dev) has no
press-release dataset, but the web app (web.quartr.com) clearly renders a
"Press releases" tab per company (confirmed by Jonas's screenshot of Baker
Hughes, companyId=3909 from an earlier MCP search_companies call). This
uses the same technique that reverse-engineered Newsweb's real API
(scripts/probe_newsweb_playwright.py): open the page in a real browser and
record every network request the frontend makes, to find whatever backend
endpoint actually populates that tab.

Critical open question: does viewing this require an authenticated Quartr
session (Jonas's login), or is company-level press-release data served
unauthenticated? If it's login-gated, this approach won't work without his
credentials/session cookie -- this probe will make that clear either way
(login redirect vs. real data in the captured responses).

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import json

from playwright.sync_api import sync_playwright

COMPANY_URL = "https://web.quartr.com/companies/3909"  # Baker Hughes, BKR
HEADERS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def probe():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=HEADERS_UA)

        def on_response(resp):
            url = resp.url
            # Only care about XHR/fetch-style API calls, not static assets.
            if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".svg", ".woff2", ".ico")):
                return
            if "api" in url.lower() or "press" in url.lower() or "news" in url.lower() or "document" in url.lower():
                captured.append((resp.status, url))

        page.on("response", on_response)

        print(f"Navigating to {COMPANY_URL} ...")
        page.goto(COMPANY_URL, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        final_url = page.url
        title = page.title()
        print(f"Landed on: {final_url}")
        print(f"Page title: {title}")
        logged_out_signal = "login" in final_url.lower() or "sign" in final_url.lower()
        print(f"Looks like a login redirect: {logged_out_signal}")

        # Try clicking the "Press releases" tab if present, to trigger any
        # lazy-loaded API call that only fires on tab click.
        try:
            page.get_by_text("Press releases", exact=False).first.click(timeout=5000)
            page.wait_for_timeout(3000)
            print("Clicked 'Press releases' tab successfully.")
        except Exception as e:
            print(f"Could not click 'Press releases' tab: {e}")

        browser.close()

    print(f"\n{len(captured)} candidate API/press/news responses captured:")
    for status, url in captured[:40]:
        print(f"  {status}  {url}")


if __name__ == "__main__":
    probe()
