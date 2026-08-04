"""One-off diagnostic: the 04 Aug 2026 digest carried an Aker Solutions/
Equinor frame-agreement item Jonas flagged as old news, not genuinely new.

Root cause found: `fetch_ir._parse_date_string`'s Norwegian-month
translation (`_NO_TO_EN_MONTH`) did a naive substring `.replace()` --
"januar" and "februar" are themselves exact prefixes of the English
"january"/"february", so a real English date like "January 8, 2026" got
silently corrupted into "Januaryy 8, 2026" before ever reaching dateutil.
dateutil's fuzzy parser can't recognize "Januaryy" as a month, drops it, and
defaults the missing month/day to *today's* -- which made a real Aker
Solutions/Equinor press release, actually published 8 January 2026, read as
"published today" on literally every single run, forever (unlike an
ordinary stale item, which ages out of the window on its own). Confirmed
live via this script: `_extract_published()` on the real akersolutions.com
news-archive anchor for that release returned '2026-08-04T00:00:00' instead
of '2026-01-08T00:00:00'. The same bug also silently dropped a *different*
real item ("February 16, 2026" -> "Februaryy 16, 2026" -> dateutil raises
IllegalMonthError, caught and swallowed as None) -- confirmed the fix
doesn't regress that path either. Fixed in `_parse_date_string` by using a
word-boundary-anchored `re.sub` instead of a plain substring replace, so
"januar"/"februar" no longer matches inside "january"/"february".

(The TGS 2D-reimaging item flagged in the same digest turned out to have a
genuine same-day (04 Aug) publish date straight from TGS's own official RSS
feed -- not a date-extraction bug. If it's still showing up as "old" after
this fix, it's a relevance-filtering question -- TGS puts out this kind of
multi-client-project-launch release roughly weekly as routine business --
not a recency bug, and would need a separate discussion about tightening
`src/draft.py`'s KEEP/DROP criteria.)

Run via a throwaway workflow_dispatch job on a runner with real network
access (this sandbox's proxy blocks tgs.com/akersolutions.com/the Newsweb
API directly) -- see README's "midlertidig workflow_dispatch-jobb" pattern.
"""
from datetime import datetime, timezone

from src.fetch_newsweb import fetch_issuer_messages
from src.fetch_ir import fetch_company_news, _extract_published, HEADERS, TIMEOUT
from src.main import lookback_cutoff, is_recent_enough
from bs4 import BeautifulSoup
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

        nw_items = fetch_issuer_messages(issuer)
        dump_recency(f"{company_id} Newsweb", nw_items)

        ir_items = fetch_company_news(company_id, ir_url)
        dump_recency(f"{company_id} IR-scrape", ir_items)

        try:
            resp = requests.get(ir_url, timeout=TIMEOUT, headers=HEADERS)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"\n  (plain GET of {ir_url} failed: {e})")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if not text or len(text) < 15 or not any(kw in text.lower() for kw in keywords):
                continue
            print(f"\n  MATCHED anchor text: {text[:120]!r}")
            print(f"  _extract_published() result: {_extract_published(a, a['href'])!r}")


if __name__ == "__main__":
    main()
