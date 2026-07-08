"""One-off diagnostic: fetch_newsweb.py only captures title + category from
the Newsweb list endpoint, never the actual disclosure body text -- which is
why drafted comments for Newsweb items are thin/wrong ('No further
transaction details were disclosed' on a TGS release that actually had a
USD 100m+ price, an earn-out, etc.). Probes for a message-detail endpoint
that returns the full body, using TGS messageId 677857 as the known-good
test case.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests

from src.fetch_newsweb import API_BASE, HEADERS, TIMEOUT

MESSAGE_ID = 677857  # TGS / Enverus divestment, known to exist

CANDIDATES = [
    f"{API_BASE}/message?messageId={MESSAGE_ID}",
    f"{API_BASE}/message/{MESSAGE_ID}",
    f"{API_BASE}/details?messageId={MESSAGE_ID}",
    f"{API_BASE}/details/{MESSAGE_ID}",
    f"{API_BASE}/attachment?messageId={MESSAGE_ID}",
    f"https://api3.oslo.oslobors.no/v1/newsreader/message/{MESSAGE_ID}",
    f"https://newsweb.oslobors.no/api/message/{MESSAGE_ID}",
]


def probe():
    # First re-confirm the list endpoint's exact shape for this message so
    # we know what fields are already available vs. missing.
    list_url = f"{API_BASE}/list?issuer=TGS"
    resp = requests.get(list_url, headers=HEADERS, timeout=TIMEOUT)
    print(f"=== {list_url} -> {resp.status_code} ===")
    payload = resp.json()
    for m in payload.get("data", {}).get("messages", []):
        if m.get("messageId") == MESSAGE_ID:
            print("full list-endpoint object for this message:")
            print(m)
    print()

    for url in CANDIDATES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            print(f"=== {url} -> {resp.status_code} ===")
            print(resp.text[:1500])
            print()
        except requests.RequestException as e:
            print(f"=== {url} -> ERROR: {e} ===\n")


if __name__ == "__main__":
    probe()
