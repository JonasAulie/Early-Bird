"""One-off diagnostic: for companies whose ir_url is broken or missing,
fetch their homepage and auto-discover likely news/press/investor links
from the actual page, instead of guessing URL paths blind. Run on a
real-network GitHub Actions runner (see README) and use the output to fix
config/watchlist.json.
"""
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
}
TIMEOUT = 20

KEYWORDS = ("news", "press", "media", "newsroom", "investor", "pressemeld")

# id -> homepage to start from (root domain, not the broken deep link)
TARGETS = {
    "patterson_uti": "https://www.patenergy.com/",
    "kongsbergmaritime": "https://www.kongsberg.com/",
    "tgs": "https://www.tgs.com/",
    "bwoffshore": "https://www.bwoffshore.com/",
    "akastor": "https://www.akastor.com/",
    "transocean": "https://www.deepwater.com/",
    "noblecorp": "https://www.noblecorp.com/",
    "seadrill": "https://www.seadrill.com/",
    "borrdrilling": "https://www.borrdrilling.com/",
    "odfjelldrilling": "https://www.odfjelldrilling.com/",
    "odfjelltechnology": "https://www.odfjelltechnology.com/",
    "cadeler": "https://www.cadeler.com/",
    "hexagoncomposites": "https://hexagongroup.com/",
    "hexagonpurus": "https://hexagonpurus.com/",
    "saudiaramco": "https://www.aramco.com/",
    # currently null ir_url
    "sedenergy": "https://www.sedenergyholdings.com/",
    "noramdrilling": "https://www.noramdrilling.no/",
    "sea1offshore": "https://www.sea1offshore.com/",
    "cavendish": "https://www.cavendishenergy.com/",
    "bonheur": "https://www.bonheur.no/",
    "integratedwind": "https://www.integratedwindsolutions.com/",
    "magnora": "https://www.magnora.com/",
    "cloudberry": "https://www.cloudberry.no/",
}


def discover(homepage_url: str):
    try:
        resp = requests.get(homepage_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        return {"error": str(e)}
    if resp.status_code != 200:
        return {"status": resp.status_code, "final_url": resp.url}

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        haystack = (href + " " + text).lower()
        if any(k in haystack for k in KEYWORDS):
            full = urljoin(resp.url, href)
            if urlparse(full).netloc == urlparse(resp.url).netloc:
                candidates.add(full)
    return {"status": resp.status_code, "final_url": resp.url, "candidates": sorted(candidates)[:15]}


if __name__ == "__main__":
    results = {}
    for company_id, url in TARGETS.items():
        print(f"\n=== {company_id} ({url}) ===")
        result = discover(url)
        results[company_id] = result
        for k, v in result.items():
            print(f"  {k}: {v}")

    Path("discover_results.json").write_text(json.dumps(results, indent=2))
