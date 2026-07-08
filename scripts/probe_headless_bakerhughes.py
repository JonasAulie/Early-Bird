"""One-off diagnostic: verify the headless-browser fallback in fetch_ir.py
rescues Baker Hughes (confirmed JS-only SPA, see scripts/probe_bakerhughes.py)
before trusting it in the full production scan. Times the fetch so we know
the real per-company cost.

History: attempt 1 timed out on 'networkidle'. Attempt 2 (domcontentloaded +
fixed 5s wait) rendered fine but the scrape still found 0 items -- a
follow-up DOM dump (probe 3) proved the real content (726 anchors, 510
headline-shaped, 'Kodiak' present) loads fine on a different run, so the
fixed wait was sometimes too short. fetch_ir.py now retries once with extra
wait before giving up; this probe re-tests that end to end.

Run via a throwaway workflow_dispatch job on a runner with Chromium
installed (playwright install --with-deps chromium).
"""
import time

from src.fetch_ir import fetch_company_news

URL = "https://www.bakerhughes.com/company/news"


def probe():
    start = time.monotonic()
    items = fetch_company_news("bakerhughes", URL)
    elapsed = time.monotonic() - start
    print(f"\nfetch_company_news('bakerhughes', {URL!r}) took {elapsed:.1f}s, found {len(items)} items:")
    for it in items:
        print(f"  published={it['published']!r}  title={it['title'][:90]!r}")
    hit = any("kodiak" in it["title"].lower() for it in items)
    print(f"\nKodiak Gas Services headline found: {hit}")


if __name__ == "__main__":
    probe()
