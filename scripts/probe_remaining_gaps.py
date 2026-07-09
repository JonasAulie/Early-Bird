"""One-off diagnostic for the final 6 companies that returned ZERO items
in scripts/probe_watchlist_coverage.py:

  chevron, saudiaramco, bakerhughes, subsea7 (has Newsweb, low priority),
  sbmoffshore, transocean

Transocean's investor.deepwater.com fails with net::ERR_HTTP2_PROTOCOL_ERROR
in both plain requests AND headless Chromium -- unusual, worth isolating
whether it's an HTTP/2-specific server quirk (force HTTP/1.1) or a dead
URL entirely. SBM Offshore hasn't been investigated at all yet. This probes
both directly, plus tries a couple of alternate URL candidates for each.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CANDIDATES = {
    "transocean": [
        "https://investor.deepwater.com/press-releases/",
        "https://investor.deepwater.com/press-releases",
        "https://www.deepwater.com/news/",
        "https://www.deepwater.com/",
    ],
    "sbmoffshore": [
        "https://www.sbmoffshore.com/newsroom/",
        "https://www.sbmoffshore.com/media/",
        "https://www.sbmoffshore.com/investors/",
        "https://www.sbmoffshore.com/investors/news-events/",
    ],
}


def probe_requests(url):
    # Force HTTP/1.1 by disabling HTTP/2 -- requests uses HTTP/1.1 by
    # default already (no h2 support without a special adapter), so this
    # tells us whether the ERR_HTTP2_PROTOCOL_ERROR seen in Playwright is
    # specific to HTTP/2 negotiation.
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        print(f"  requests.get -> {resp.status_code}  final_url={resp.url}  len={len(resp.text)}")
        return resp.text
    except requests.RequestException as e:
        print(f"  requests.get -> ERROR: {e}")
        return None


def probe_headless_http1(url):
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            # --disable-http2 forces the browser to negotiate HTTP/1.1 only,
            # to check if that avoids the protocol error seen with default
            # (HTTP/2-enabled) Chromium.
            browser = p.chromium.launch(args=["--disable-http2"])
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
        print(f"  headless(--disable-http2) -> rendered {len(html)} bytes")
        return html
    except Exception as e:
        print(f"  headless(--disable-http2) -> ERROR: {e}")
        return None


if __name__ == "__main__":
    for company_id, urls in CANDIDATES.items():
        print(f"=== {company_id} ===")
        for url in urls:
            print(f" {url}")
            probe_requests(url)
        print()

    print("=== HTTP/1.1-forced headless retry for the currently-configured URLs ===")
    for company_id, urls in CANDIDATES.items():
        url = urls[0]
        print(f"{company_id}: {url}")
        probe_headless_http1(url)
        print()
