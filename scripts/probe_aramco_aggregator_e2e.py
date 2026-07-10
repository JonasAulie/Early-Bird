"""End-to-end verification of the new Google/Bing News RSS fallback for
Saudi Aramco: fetch via fetch_news_aggregator(), apply the real recency
filter, then run the real relevance-filter/drafter on whatever survives,
to confirm the whole pipeline (not just the raw RSS fetch) produces sane
output and that aggregator noise (third-party analyst pieces, tangential
mentions) gets correctly filtered out rather than flooding the digest.

Run via a throwaway workflow_dispatch job on a runner with real network +
secrets access.
"""
from datetime import datetime, timezone

from src.fetch_news_aggregator import fetch_news_aggregator
from src.main import is_recent_enough, lookback_cutoff
from src.draft import draft_entries
from src.watchlist import load_companies


def main():
    companies = {c["id"]: c for c in load_companies()}
    aramco = companies["saudiaramco"]

    now = datetime.now(timezone.utc)
    cutoff = lookback_cutoff(now)
    print(f"cutoff: {cutoff}")

    items = fetch_news_aggregator(aramco["news_aggregator_query"], aramco["id"])
    print(f"fetched {len(items)} raw items")

    candidates = []
    for item in items:
        recent = is_recent_enough(item.get("published"), cutoff)
        print(f"  recent={recent!s:5s}  published={item.get('published')!r}  "
              f"source={item['source']!r}  title={item['title'][:80]!r}")
        if recent:
            item["company"] = aramco["name"]
            item["recommendation"] = aramco.get("recommendation")
            candidates.append(item)

    print(f"\n{len(candidates)} candidates within recency window")
    if not candidates:
        print("nothing to draft, stopping")
        return

    entries = draft_entries(candidates)
    print(f"\ndraft_entries returned {len(entries)} entries")
    kept_urls = {e.get("url") for e in entries}
    for e in entries:
        print(f"\nKEPT headline: {e.get('headline')}")
        print(f"  comment: {e.get('comment')}")
    for c in candidates:
        if c["url"] not in kept_urls:
            print(f"\nDROPPED: {c['title'][:100]!r} (source={c['source']!r})")


if __name__ == "__main__":
    main()
