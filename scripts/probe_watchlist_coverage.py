"""One-off diagnostic: run the real fetch_company_news() against every
company in config/watchlist.json that has an ir_url, and report which ones
return zero items (i.e. currently contribute nothing to Early Bird via the
IR path) vs. which return items. This gives a definitive, current list to
work through -- rather than relying on scattered NOTE/WARNING lines from
past production run logs.

Note: Newsweb-covered companies (newsweb_issuer set) still get IR-page
coverage checked here too, since main.py fetches both paths as
complementary sources -- a company can be "fine" overall via Newsweb even
if its IR path returns zero, so cross-reference against newsweb_issuer
before treating a zero-IR result as a real gap.

Pass company IDs as CLI args to check only specific companies (fast
re-verification after a targeted fix) instead of the full watchlist.

Run via a throwaway workflow_dispatch job on a runner with real network
access. Full sweep takes a while (up to ~10s per company that needs the
headless fallback), so expect several minutes total for all ~50
IR-having companies.
"""
import sys
import time

from src.fetch_ir import fetch_company_news
from src.watchlist import load_companies


def probe(only_ids=None):
    companies = load_companies()
    zero = []
    ok = []
    for c in companies:
        if not c.get("ir_url"):
            continue
        if only_ids and c["id"] not in only_ids:
            continue
        start = time.monotonic()
        try:
            items = fetch_company_news(c["id"], c["ir_url"])
        except Exception as e:
            print(f"{c['id']:24s} EXCEPTION: {e}")
            zero.append((c["id"], c.get("newsweb_issuer"), c["ir_url"]))
            continue
        elapsed = time.monotonic() - start
        dated = sum(1 for it in items if it.get("published"))
        status = "OK" if items else "ZERO"
        print(f"{c['id']:24s} {status:5s} n={len(items):3d} dated={dated:3d} "
              f"({elapsed:5.1f}s) newsweb={c.get('newsweb_issuer')}")
        for it in items[:3]:
            print(f"    published={it.get('published')!r}  title={it['title'][:80]!r}")
        if not items:
            zero.append((c["id"], c.get("newsweb_issuer"), c["ir_url"]))
        else:
            ok.append(c["id"])

    print(f"\n{'='*70}")
    print(f"{len(ok)} companies returned items, {len(zero)} returned ZERO from IR path:")
    for company_id, newsweb, url in zero:
        newsweb_note = f" (has Newsweb: {newsweb})" if newsweb else " (NO Newsweb -- IR is the only path!)"
        print(f"  {company_id:24s}{newsweb_note}  url={url}")


if __name__ == "__main__":
    ids = set(sys.argv[1:]) or None
    probe(ids)
