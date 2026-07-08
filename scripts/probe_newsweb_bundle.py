"""One-off diagnostic: download Newsweb's React JS bundle and grep it for
the real API base URL, since the site itself is a pure SPA (see
scripts/probe_urls.py's earlier findings) and can't be read by a plain
requests.get(). CRA/webpack bundles usually have the API base URL as a
plain string literal, so this is often enough without needing a full
headless browser.

Run via a throwaway workflow_dispatch job (see README) on a runner with
real network access -- this session's environment doesn't have one.
"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

PAGE_URL = "https://newsweb.oslobors.no/"


def main():
    resp = requests.get(PAGE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text
    print("=== index.html ===")
    print(html[:2000])

    js_paths = re.findall(r'src="(/static/js/[^"]+\.js)"', html)
    css_paths = re.findall(r'href="(/static/css/[^"]+\.css)"', html)
    print(f"\nFound JS bundles: {js_paths}")
    print(f"Found CSS bundles: {css_paths}")

    for path in js_paths:
        url = "https://newsweb.oslobors.no" + path
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"\n=== {url} -> {r.status_code}, {len(r.text)} bytes ===")
        body = r.text

        # Look for anything that smells like an API base URL.
        candidates = set()
        for pattern in [
            r'https?://[a-zA-Z0-9\.\-]+\.oslobors\.no[a-zA-Z0-9\./_\-]*',
            r'https?://[a-zA-Z0-9\.\-]+\.euronext\.com[a-zA-Z0-9\./_\-]*',
            r'https?://api[a-zA-Z0-9\.\-]*\.[a-zA-Z0-9\.\-]+[a-zA-Z0-9\./_\-]*',
            r'"baseURL"\s*:\s*"([^"]+)"',
            r'"apiUrl"\s*:\s*"([^"]+)"',
            r'REACT_APP_[A-Z_]+["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]:
            for m in re.finditer(pattern, body):
                candidates.add(m.group(0))

        print(f"Candidate API-ish strings found ({len(candidates)}):")
        for c in sorted(candidates)[:80]:
            print("  ", c)


if __name__ == "__main__":
    main()
