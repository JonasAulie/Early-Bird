"""Investigate why two real stories (SLB/OneSubsea Kutei North Hub umbilical
award, and a broader "Baker Hughes secures LNG equipment & services awards
for Cheniere's Sabine Pass" story bundling three separate awards) didn't
show up in the automated Early Bird output on 2026-07-10, when the user
saw them in the real (human-written) Early Bird issue.

Fetches both companies' raw candidate lists directly (bypassing main.py's
recency/dedup filtering) so we can see exactly what's on their IR pages
right now: titles, dates, URLs. Cross-reference against state/seen.json to
check if a similar/duplicate item was already sent on 2026-07-09.

Run via a throwaway workflow_dispatch job on a runner with real network
access.
"""
from src.fetch_ir import fetch_company_news
from src.state import load_seen, item_id
from src.watchlist import load_companies


def main():
    companies = {c["id"]: c for c in load_companies()}
    seen_ids = load_seen()
    print(f"total seen_ids: {len(seen_ids)}")

    for company_id in ["slb", "bakerhughes"]:
        c = companies[company_id]
        print(f"\n{'='*20} {c['name']} ({company_id}) {'='*20}")
        print(f"ir_url: {c.get('ir_url')}")
        print(f"newsweb_issuer: {c.get('newsweb_issuer')}")
        items = fetch_company_news(c["id"], c["ir_url"])
        print(f"fetched {len(items)} items")
        for it in items:
            iid = item_id(it["url"], it["title"])
            is_seen = iid in seen_ids
            print(f"  published={it.get('published')!r}  seen={is_seen}  "
                  f"title={it['title'][:90]!r}")
            print(f"    url={it['url']}")


if __name__ == "__main__":
    main()
