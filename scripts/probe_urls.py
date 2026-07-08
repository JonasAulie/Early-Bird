"""One-off diagnostic tool: runs on the GitHub Actions runner (which has
real internet access, unlike the Claude Code session that wrote this repo)
to test a batch of candidate URLs and print status codes + response
snippets. Used to reverse-engineer the real Newsweb API and fix broken IR
URLs without guessing blind.

Run via the 'probe' workflow_dispatch input on early-bird.yml, or locally:
    python -m scripts.probe_urls
"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
}

NEWSWEB_CANDIDATES = [
    "https://newsweb.oslobors.no/",
    "https://newsweb.oslobors.no/api/messages?issuer=EQNR",
    "https://newsweb.oslobors.no/api/message/list?issuer=EQNR",
    "https://newsweb.oslobors.no/search?issuer=EQNR",
    "https://api2.oslobors.no/newsweb/api/messages?issuer=EQNR",
    "https://api.oslobors.no/newsweb/api/messages?issuer=EQNR",
    "https://live.euronext.com/en/products/equities/NO0010096985-XOSL",
    "https://live.euronext.com/en/company/EQUINOR-ASA/news",
    "https://www.euronext.com/en/news?company=EQNR",
]

IR_URL_CANDIDATES = [
    "https://www.eni.com/en-IT/media.html",
    "https://www.repsol.com/en/press-room/press-releases/index.cshtml",
    "https://www.weatherford.com/en/news/",
    "https://www.patenergy.com/news",
    "https://www.sbmoffshore.com/newsroom/",
    "https://www.deepwater.com/newsroom/",
    "https://www.valaris.com/investors",
    "https://www.noblecorp.com/news-media",
    "https://www.seadrill.com/newsroom",
    "https://www.orronenergy.com/en/press-releases/",
    "https://orron.com/en/press-releases/",
]


def probe(urls):
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            print(f"\n=== {url} -> {resp.status_code} (final: {resp.url}) ===")
            print(resp.text[:600].replace("\n", " "))
        except requests.RequestException as e:
            print(f"\n=== {url} -> ERROR: {e} ===")


if __name__ == "__main__":
    print("########## NEWSWEB CANDIDATES ##########")
    probe(NEWSWEB_CANDIDATES)
    print("\n########## IR URL CANDIDATES ##########")
    probe(IR_URL_CANDIDATES)
