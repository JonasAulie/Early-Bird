"""Orchestrates one Early Bird scan run:

  1. Load watchlist.
  2. Fetch latest announcements per company (Newsweb for Oslo Bors names,
     generic IR/RSS fetch for everyone else).
  3. Keep only items published within the lookback window (since 08:30 Oslo
     the day before, or Friday 08:30 on Mondays). This is the ONLY filter on
     what can appear in an email -- there is deliberately no persistent
     "already sent" blacklist, so the same relevant item legitimately
     reappears in every run whose window still covers it. Concretely: both
     the 07:32 and 08:02 Oslo runs on a given day share the same window and
     will both carry the same item, and it can carry into the next day's
     two runs too if it's still within their own window. This is by design
     (Jonas: items must never be silently "used up" by an earlier send --
     completeness across all runs in the window matters more than avoiding
     repetition).
  4. Ask Claude to filter for relevance and draft headline + comment.
  5. Email the result via Resend (skipped if nothing relevant was found).

Run with: python -m src.main
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from dateutil import parser as dateparser

from src.watchlist import load_companies
from src.fetch_newsweb import fetch_issuer_messages
from src.fetch_ir import fetch_company_news, fetch_article_body
from src.fetch_news_aggregator import fetch_news_aggregator
from src.draft import draft_entries
from src.emailer import send_digest
from src.schedule_guard import should_run_now


def lookback_cutoff(now_utc: datetime) -> datetime:
    """Early Bird goes out ~08:30 Oslo time, so the relevant window is
    'since yesterday's 08:30 Oslo' -- not a rolling 24h from whenever this
    particular run happens to fire. On Mondays, back up to last Friday
    08:30 so weekend news isn't missed."""
    oslo = ZoneInfo("Europe/Oslo")
    local_now = now_utc.astimezone(oslo)
    days_back = 3 if local_now.weekday() == 0 else 1  # Monday -> back to Friday
    cutoff_date = local_now - timedelta(days=days_back)
    cutoff_local = cutoff_date.replace(hour=8, minute=30, second=0, microsecond=0)
    return cutoff_local.astimezone(timezone.utc)


def _parsed_datetime(published_raw):
    """Parses `published_raw` to a tz-aware datetime, or None if missing/
    unparseable. Shared by is_recent_enough and the bare-date dedup below so
    both agree on what counts as a real (non-midnight-default) timestamp."""
    if not published_raw:
        return None
    try:
        dt = dateparser.parse(published_raw)
    except (ValueError, OverflowError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _has_time_of_day(published_raw) -> bool:
    dt = _parsed_datetime(published_raw)
    return dt is not None and dt.timetz().replace(tzinfo=None) != time(0, 0)


def is_recent_enough(published_raw, cutoff: datetime) -> bool:
    dt = _parsed_datetime(published_raw)
    if dt is None:
        # No verifiable publish date. Without dedup as a safety net anymore,
        # an undated item can NEVER be excluded once it's stale, so if we
        # can't confirm it's inside the window, drop it. fetch_ir works
        # hard to extract a date, so real new items still carry one.
        return False
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


def _dedupe_bare_date_duplicates(items):
    """Same company, same calendar date, one source with a precise
    time-of-day and another with only a bare date (defaults to midnight --
    see is_recent_enough) almost always means the same underlying
    announcement reported twice: once via Newsweb's precise disclosure
    timestamp, once via the company's own news-listing page, which often
    only shows a date. The bare-date copy then gets is_recent_enough's
    "whole day counts" benefit-of-the-doubt fallback, which lets it survive
    one calendar day longer than the real (precise) timestamp would allow
    -- confirmed live: a DOF Group letter-of-award, published before the
    08:30 cutoff and correctly excluded via its precise Newsweb timestamp,
    still reappeared the next morning via its bare-date dof.no duplicate.
    Drop the bare-date copy whenever a precisely-timed sibling from the same
    company already covers that date. Companies with no precise sibling at
    all (the common case for IR-only, non-Newsweb names) are unaffected --
    the whole-day fallback stays intact there, which is what it exists for
    (see is_recent_enough)."""
    precise_dates = set()
    for item in items:
        if _has_time_of_day(item.get("published")):
            dt = _parsed_datetime(item.get("published"))
            precise_dates.add(dt.date())
    if not precise_dates:
        return items
    out = []
    for item in items:
        raw = item.get("published")
        if raw and not _has_time_of_day(raw):
            dt = _parsed_datetime(raw)
            if dt and dt.date() in precise_dates:
                continue
        out.append(item)
    return out


def collect_candidates(companies, cutoff):
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
        # Fallback for companies whose own site is a confirmed network-level
        # WAF/IP-reputation block that no scraping technique from this
        # environment can get past (see watchlist.json comment context and
        # scripts/probe_aramco_subsea7*.py) -- Google/Bing News RSS run on
        # infrastructure the block doesn't target, and surface real
        # corporate news the direct path can never see.
        if company.get("news_aggregator_query"):
            items.extend(fetch_news_aggregator(company["news_aggregator_query"], company["id"]))

        items = _dedupe_bare_date_duplicates(items)

        for item in items:
            if not is_recent_enough(item.get("published"), cutoff):
                continue
            item["company"] = company["name"]
            item["recommendation"] = company.get("recommendation")
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

    candidates = collect_candidates(companies, cutoff)
    print(f"[main] {len(candidates)} candidate items after recency filtering")
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
            print(f"[main] ERROR: failed to send digest email: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[main] FATAL: {e}", file=sys.stderr)
        raise
