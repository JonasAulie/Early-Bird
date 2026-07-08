"""Probe the real Newsweb API base URL found by probe_newsweb_bundle.py
(REACT_APP_API_URL="https://obns-api.dev.euronext.cloud/") for the actual
issuer-filtered messages endpoint and response shape.
"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

BASE = "https://obns-api.dev.euronext.cloud"

CANDIDATE_PATHS = [
    "/",
    "/messages",
    "/messages?issuer=EQNR",
    "/api/messages",
    "/api/messages?issuer=EQNR",
    "/v1/messages",
    "/v1/messages?issuer=EQNR",
    "/newsweb/messages",
    "/newsweb/api/messages",
    "/message?issuer=EQNR",
    "/search?issuer=EQNR",
    "/search/messages?issuer=EQNR",
]

for path in CANDIDATE_PATHS:
    url = BASE + path
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        print(f"\n=== {url} -> {r.status_code} ===")
        print(r.text[:800])
    except requests.RequestException as e:
        print(f"\n=== {url} -> ERROR: {e} ===")
