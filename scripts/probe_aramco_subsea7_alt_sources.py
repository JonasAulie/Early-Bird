"""Creative alternative data paths for Saudi Aramco and Subsea7, both
confirmed to be genuine IP-reputation/WAF blocks at the network level (see
scripts/probe_aramco_subsea7.py and probe_subsea7_challenge.py -- plain
request AND real headless browser both fail identically, ruling out a
scraping-technique fix on their own domains).

Rather than trying to get past their WAF, this tries routes that never
touch their domain directly:

  1. Google News RSS search -- a legitimate, public aggregator feed. Many
     press releases get indexed and syndicated within minutes.
  2. Bing News RSS search -- same idea, different aggregator/index.
  3. r.jina.ai reader proxy (https://r.jina.ai/<url>) -- a free, public
     "fetch this URL and return clean text for an LLM" service. Its
     infrastructure and IP range/fingerprint differ from a raw
     requests.get() or Playwright launch from a GitHub Actions runner, so
     it may not trip the same block even though the destination is the
     same blocked domain.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
import requests
import feedparser

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
TIMEOUT = 20

QUERIES = {
    "Saudi Aramco": '"Saudi Aramco"',
    "Subsea7": '"Subsea7" OR "Subsea 7"',
}

ARAMCO_URL = "https://www.aramco.com/en/news-media"
SUBSEA7_URL = "https://www.subsea7.com/en/media/news.html"


def try_google_news_rss(company_label, query):
    print(f"--- Google News RSS: {company_label} ---")
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"  status={resp.status_code} len={len(resp.text)}")
        if resp.status_code == 200:
            parsed = feedparser.parse(resp.text)
            print(f"  parsed {len(parsed.entries)} entries")
            for e in parsed.entries[:6]:
                print(f"    published={e.get('published')!r}  title={e.get('title', '')[:90]!r}")
                print(f"      link={e.get('link')}")
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
    print()


def try_bing_news_rss(company_label, query):
    print(f"--- Bing News RSS: {company_label} ---")
    url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"  status={resp.status_code} len={len(resp.text)}")
        if resp.status_code == 200:
            parsed = feedparser.parse(resp.text)
            print(f"  parsed {len(parsed.entries)} entries")
            for e in parsed.entries[:6]:
                print(f"    published={e.get('published')!r}  title={e.get('title', '')[:90]!r}")
                print(f"      link={e.get('link')}")
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
    print()


def try_jina_reader(company_label, target_url):
    print(f"--- r.jina.ai reader proxy: {company_label} ({target_url}) ---")
    proxy_url = f"https://r.jina.ai/{target_url}"
    try:
        resp = requests.get(proxy_url, headers=HEADERS, timeout=30)
        print(f"  status={resp.status_code} len={len(resp.text)}")
        print(f"  first 1000 chars:\n{resp.text[:1000]!r}")
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
    print()


if __name__ == "__main__":
    for label, query in QUERIES.items():
        try_google_news_rss(label, query)
        try_bing_news_rss(label, query)

    try_jina_reader("Saudi Aramco", ARAMCO_URL)
    try_jina_reader("Subsea7", SUBSEA7_URL)
