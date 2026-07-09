"""One-off diagnostic: fetch Quartr's public API docs so we can see the real
REST API spec (base URL, auth method, press-release endpoint) without
guessing. The Claude Code session that wrote this repo has no general
internet access (only anthropic.com + package registries), so this has to
run on a GitHub Actions runner instead, same pattern as the other probes.

v2: the introduction page confirmed the 8 official datasets (Events, Live
audio, Live transcripts, Backlog audio, Backlog transcripts, Filings and
reports, Slide presentations, Event summaries) do NOT include a dedicated
press-release dataset -- matches the earlier MCP-tool finding (list_documents
documentTypes=["press_release"] returned almost nothing). This fetches the
actual API reference pages (on the quartr.dev domain, separate from
quartr.com/docs) for auth + the Documents/Companies endpoints to confirm
exactly what's queryable, and the REST-API auth/fetching-data guide pages.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

URLS = [
    "https://quartr.com/docs/rest-api/auth",
    "https://quartr.com/docs/rest-api/fetching-data",
    "https://quartr.dev/api-reference/documents",
    "https://quartr.dev/api-reference/companies",
    "https://quartr.com/docs/datasets/filings-and-reports",
]


def fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        print(f"=== GET {url} -> {resp.status_code}  len={len(resp.text)} ===")
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
        print(text[:4000])
        print()
    except requests.RequestException as e:
        print(f"=== GET {url} -> ERROR: {e} ===\n")


if __name__ == "__main__":
    for url in URLS:
        fetch(url)
