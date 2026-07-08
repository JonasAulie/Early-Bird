"""Load newsweb.oslobors.no in a real (headless) browser and record every
network response, so we can see what API calls the React app actually
makes at runtime -- the REACT_APP_API_URL baked into the JS bundle
(obns-api.dev.euronext.cloud) turned out to be a dead/internal dev host,
so this is the fallback approach: watch real traffic instead of guessing.

Requires: pip install playwright && playwright install --with-deps chromium
"""
import json
from playwright.sync_api import sync_playwright

TARGET_URL = "https://newsweb.oslobors.no/search?issuer=EQNR"

responses = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if "static" in url or url.endswith((".css", ".png", ".svg", ".ico", ".woff", ".woff2")):
                return
            entry = {"url": url, "status": response.status, "content_type": ct}
            if "json" in ct:
                try:
                    body = response.json()
                    entry["body_preview"] = json.dumps(body)[:1500]
                except Exception as e:
                    entry["body_error"] = str(e)
            responses.append(entry)

        page.on("response", on_response)

        print(f"Navigating to {TARGET_URL} ...")
        page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # let any delayed XHR calls finish

        print(f"\nCaptured {len(responses)} non-static responses:\n")
        for r in responses:
            print(f"{r['status']}  {r['content_type']:30s}  {r['url']}")
            if "body_preview" in r:
                print("   body:", r["body_preview"])
            if "body_error" in r:
                print("   body_error:", r["body_error"])

        browser.close()


if __name__ == "__main__":
    main()
