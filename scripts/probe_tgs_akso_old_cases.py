"""One-off diagnostic: the 04 Aug 2026 digest carried a TGS 2D-reimaging
item and an Aker Solutions/Equinor frame-agreement item that Jonas flagged
as old news, not genuinely new. Dumps, for both TGS and Aker Solutions:

  1. Raw Newsweb messages (precise publishedTime) for the issuer.
  2. Raw IR-page-scrape output (fetch_company_news), including which
     anchor/date-extraction path each item's `published` came from.
  3. Whether each item would currently pass is_recent_enough() for both the
     morning (preview=False) and 16:00 preview (preview=True) cutoffs.
  4. For the two flagged headlines specifically (matched by keyword), the
     raw HTML snippet around the anchor that _extract_published() worked
     from, so we can see exactly which date string got picked up and why.

Run via a throwaway workflow_dispatch job on a runner with real network
access (this sandbox's proxy blocks tgs.com/akersolutions.com/the Newsweb
API directly) -- see README's "midlertidig workflow_dispatch-jobb" pattern.
"""
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.fetch_newsweb import fetch_issuer_messages
from src.fetch_ir import fetch_company_news, HEADERS, TIMEOUT, _extract_published, _attr_date_in, _DATE_ATTRS
from src.main import lookback_cutoff, is_recent_enough
import requests

TARGETS = [
    ("tgs", "TGS", "https://www.tgs.com/press-releases", ["reimaging", "egy-2dre", "egas"]),
    ("akersolutions", "AKSO", "https://www.akersolutions.com/news/",
     ["equinor", "frame agreement", "maintenance"]),
]


def dump_recency(label, items):
    now = datetime.now(timezone.utc)
    cutoff_morning = lookback_cutoff(now, preview=False)
    cutoff_preview = lookback_cutoff(now, preview=True)
    print(f"\n--- {label}: recency check (now={now.isoformat()}) ---")
    print(f"    morning cutoff={cutoff_morning.isoformat()}  preview cutoff={cutoff_preview.isoformat()}")
    for it in items:
        rm = is_recent_enough(it.get("published"), cutoff_morning, now)
        rp = is_recent_enough(it.get("published"), cutoff_preview, now)
        print(f"  morning={rm!s:5} preview={rp!s:5}  published={it.get('published')!r}  "
              f"title={it['title'][:90]!r}")


def main():
    for company_id, issuer, ir_url, keywords in TARGETS:
        print(f"\n{'=' * 70}\n{company_id} (Newsweb issuer={issuer})\n{'=' * 70}")

        print(f"\n--- raw Newsweb messages ---")
        nw_items = fetch_issuer_messages(issuer)
        for it in nw_items[:20]:
            print(f"  published={it.get('published')!r}  title={it['title'][:90]!r}  url={it['url']}")
        dump_recency(f"{company_id} Newsweb", nw_items)

        print(f"\n--- raw IR-scrape items ({ir_url}) ---")
        ir_items = fetch_company_news(company_id, ir_url)
        for it in ir_items[:20]:
            print(f"  published={it.get('published')!r}  title={it['title'][:90]!r}  url={it['url']}  "
                  f"source={it.get('source')!r}")
        dump_recency(f"{company_id} IR-scrape", ir_items)

        # Find the flagged headline(s) and show the raw HTML the date came from.
        try:
            resp = requests.get(ir_url, timeout=TIMEOUT, headers=HEADERS)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"\n  (plain GET of {ir_url} failed: {e} -- can't show raw HTML snippet)")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        matched_any = False
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if not text or len(text) < 15:
                continue
            if not any(kw in text.lower() for kw in keywords):
                continue
            matched_any = True
            print(f"\n  MATCHED anchor text: {text[:120]!r}")
            print(f"  href: {a['href']}")
            extracted = _extract_published(a, a["href"])
            print(f"  _extract_published() result: {extracted!r}")
            # Walk up 3 ancestors like _extract_published does, dumping each
            # scope's raw text so we can see exactly what date string (if
            # any) it's picking up and from where.
            node = a
            for depth in range(3):
                if node is None:
                    break
                snippet = node.get_text(" ", strip=True)[:200]
                attr_hit = _attr_date_in(node)
                print(f"    ancestor[{depth}] ({node.name}): text={snippet!r}  _attr_date_in={attr_hit!r}")
                print(f"      raw HTML: {str(node)[:600]!r}")
                node = node.parent
        if not matched_any:
            print(f"\n  (no anchor on the current page matched keywords {keywords} -- "
                  f"item may have scrolled off the listing already)")


if __name__ == "__main__":
    main()
