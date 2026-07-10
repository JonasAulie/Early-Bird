"""Orchestrates one Early Bird scan run:

  1. Load watchlist + dedup state.
  2. Fetch latest announcements per company (Newsweb for Oslo Bors names,
     generic IR/RSS fetch for everyone else).
  3. Keep only items published within the lookback window (1 day, or back
     to Saturday if today is Monday) that haven't been emailed already.
  4. Ask Claude to filter for relevance and draft headline + comment.
  5. Email the result via Resend (skipped if nothing relevant was found).
  6. Persist updated dedup state.

Run with: python -m src.main
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone
from dateutil import parser as dateparser

from src.watchlist import load_companies
from src.state import load_seen, save_seen, item_id
from src.fetch_newsweb import fetch_issuer_messages
from src.fetch_ir import fetch_company_news, fetch_article_body
from src.draft import draft_entries
from src.emailer import send_digest
from src.schedule_guard import should_run_now


def lookback_cutoff(now_utc: datetime) -> datetime:
    """Early Bird goes out ~08:30 Oslo time, so the relevant window is
    'since yesterday's 08:30 Oslo' -- not a rolling 24h from whenever this
    particular run happens to fire. On Mondays, back up to last Friday
    08:30 so weekend news isn't missed."""
    from zoneinfo import ZoneInfo
    oslo = ZoneInfo("Europe/Oslo")
    local_now = now_utc.astimezone(oslo)
    days_back = 3 if local_now.weekday() == 0 else 1  # Monday -> back to Friday
    cutoff_date = local_now - timedelta(days=days_back)
    cutoff_local = cutoff_date.replace(hour=8, minute=30, second=0, microsecond=0)
    return cutoff_local.astimezone(timezone.utc)


def is_recent_enough(published_raw, cutoff: datetime) -> bool:
    if not published_raw:
        # No verifiable publish date. Relying on dedup alone (the old
        # behaviour) meant the first crawl of any page dumped its whole
        # front page of *old* headlines as if they were new -- that's what
        # sent three stale SED Energy items -- and it wasted tokens shipping
        # stale headlines to the model. If we can't confirm it's inside the
        # window, drop it. fetch_ir now works hard to extract a date, so real
        # new items still carry one.
        return False
    try:
        dt = dateparser.parse(published_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.timetz().replace(tzinfo=None) == time(0, 0):
            # Most IR-scraped sources (unlike Newsweb) only give a bare
            # calendar date, no time-of-day -- fetch_ir._parse_date_string
            # defaults those to midnight. Comparing that midnight timestamp
            # directly against an 08:30 cutoff means an item genuinely
            # published "yesterday" always reads as yesterday-00:00, which
            # is *before* yesterday's 08:30 cutoff -- so it gets silently
            # dropped on every single day's run, permanently, regardless of
            # which run processes it. Confirmed live: a real SLB/OneSubsea
            # deal and a Baker Hughes/Kodiak Gas Services deal both never
            # made it into any digest because of this. For date-only items,
            # compare by calendar date instead so the whole day counts.
            return dt.date() >= cutoff.date()
        return dt >= cutoff
    except (ValueError, OverflowError):
        return False


def collect_candidates(companies, cutoff, seen_ids):
    candidates = []
    for company in companies:
        items = []
        if company.get("newsweb_issuer"):
            items.extend(fetch_issuer_messages(company["newsweb_issuer"]))
        # Newsweb doesn't cover every disclosure a company makes (e.g. some
        # non-regulatory press releases), so always also fetch the
        # company's own IR page as a complement rather than treating
        # newsweb_issuer and ir_url as mutually exclusive.
        if company.get("ir_url"):
            items.extend(fetch_company_news(company["id"], company["ir_url"]))

        for item in items:
            if not is_recent_enough(item.get("published"), cutoff):
                continue
            iid = item_id(item["url"], item["title"])
            if iid in seen_ids:
                continue
            item["company"] = company["name"]
            item["recommendation"] = company.get("recommendation")
            item["_id"] = iid
            candidates.append(item)
    return candidates


def render_html(entries) -> str:
    today = datetime.now().strftime("%d %B %Y")
    rows = []
    for e in entries:
        rows.append(
            f'<p><b>{e["headline"]}</b><br/>{e["comment"]} '
            f'<a href="{e["url"]}">[kilde]</a></p>'
        )
    body = "\n".join(rows) if rows else "<p>Ingen relevante saker funnet i denne kjøringen.</p>"
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px;">
      <h2>Early Bird -- kandidatsaker ({today})</h2>
      {body}
      <p style="color:#888; font-size: 12px;">Automatisk generert utkast. Kvalitetssikre før bruk i rapporten.
      Husk å sjekke Upstream, Petrodata og Bloomberg manuelt — disse dekkes ikke av denne jobben.</p>
    </div>
    """


def main():
    now = datetime.now(timezone.utc)

    force = os.environ.get("FORCE_RUN", "").lower() == "true"
    if not force and not should_run_now(now):
        print("[main] outside of the 4 target Oslo-time slots, skipping (DST-safe no-op)")
        return
    if force:
        print("[main] FORCE_RUN set, bypassing the Oslo-time slot check")

    cutoff = lookback_cutoff(now)

    companies = load_companies()
    seen_ids = load_seen()

    candidates = collect_candidates(companies, cutoff, seen_ids)
    print(f"[main] {len(candidates)} candidate items after recency+dedup filtering")
    for c in candidates:
        print(f"[main]   candidate: company={c['company']!r} published={c.get('published')!r} "
              f"title={c['title'][:100]!r}")

    if not candidates:
        print("[main] nothing new, skipping email")
        return

    # IR-scrape candidates only ever carry a bare headline (see
    # fetch_ir._scrape_listing -- summary is always None); Newsweb items
    # already have a full disclosure body attached at fetch time. Fetch the
    # real article text now, for this small already-filtered candidate list
    # only, so the drafter has enough grounding to write a proper multi-
    # sentence comment instead of a one-line placeholder.
    for c in candidates:
        if not c.get("summary"):
            c["summary"] = fetch_article_body(c["url"], label=c["company"])

    entries = draft_entries(candidates)
    print(f"[main] {len(entries)} entries kept after relevance filtering")
    kept_urls = {e.get("url") for e in entries}
    for e in entries:
        print(f"[main]   kept: headline={e.get('headline')!r}")
    for c in candidates:
        if c["url"] not in kept_urls:
            print(f"[main]   dropped by relevance filter: company={c['company']!r} title={c['title'][:100]!r}")

    if entries:
        html = render_html(entries)
        subject = f"Early Bird utkast -- {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        try:
            send_digest(subject, html)
        except Exception as e:
            # Don't let an email failure blow away dedup state / fail the
            # whole run -- log it loudly and keep going. The next successful
            # run's state save is what prevents these items from piling up.
            print(f"[main] ERROR: failed to send digest email: {e}", file=sys.stderr)

    # Mark fetched candidates as seen so irrelevant IR-scrape noise doesn't
    # get re-evaluated (and re-cost tokens) every run. But Newsweb items are
    # rare, official regulatory disclosures, not high-volume noise -- a single
    # LLM relevance-filter miss must not permanently bury a real corporate
    # disclosure with no way to recover (this is exactly what happened to a
    # TGS divestment announcement: the model wrongly dropped it once, it got
    # marked seen anyway, and it silently vanished for good). So only mark a
    # Newsweb item seen once it's actually been kept (and thus sent) -- a
    # missed one gets another chance on the next run until it ages out of the
    # recency window.
    for c in candidates:
        is_newsweb = c["source"].startswith("Newsweb")
        if not is_newsweb or c["url"] in kept_urls:
            seen_ids.add(c["_id"])
    save_seen(seen_ids)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[main] FATAL: {e}", file=sys.stderr)
        raise
