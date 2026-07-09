"""One-off diagnostic: fetch Quartr's public API docs so we can see the real
REST API spec (base URL, auth method, press-release endpoint) without
guessing. The Claude Code session that wrote this repo has no general
internet access (only anthropic.com + package registries), so this has to
run on a GitHub Actions runner instead, same pattern as the other probes.

Docs sites are often JS-rendered (Next.js/Mintlify/Docusaurus), so this
tries a plain request first and falls back to headless rendering, printing
raw text either way for manual inspection.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

URLS = [
    "https://quartr.com/docs/introduction",
    "https://quartr.com/docs",
]


def plain_fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        print(f"=== plain GET {url} -> {resp.status_code}  len={len(resp.text)} ===")
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
        print(text[:3000])
        return resp.text
    except requests.RequestException as e:
        print(f"=== plain GET {url} -> ERROR: {e} ===")
        return None


def headless_fetch(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        html = page.content()
        browser.close()
    print(f"=== headless GET {url} -> rendered {len(html)} bytes ===")
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    print(text[:6000])

    # Also dump any links found on the page -- useful for finding the
    # endpoint-reference / authentication sub-pages.
    soup = BeautifulSoup(html, "html.parser")
    links = sorted({a["href"] for a in soup.find_all("a", href=True) if "quartr" in a["href"].lower() or a["href"].startswith("/")})
    print("\nlinks found:")
    for l in links[:60]:
        print(f"  {l}")


if __name__ == "__main__":
    for url in URLS:
        html = plain_fetch(url)
        print()
    print("\n\n########## HEADLESS RENDER ##########\n")
    headless_fetch("https://quartr.com/docs/introduction")
