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
import sys
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

from src.watchlist import load_companies
from src.state import load_seen, save_seen, item_id
from src.fetch_newsweb import fetch_issuer_messages
from src.fetch_ir import fetch_company_news
from src.draft import draft_entries
from src.emailer import send_digest
from src.schedule_guard import should_run_now


def lookback_cutoff(now_utc: datetime) -> datetime:
    """1 day back normally; back to Saturday if today is Monday (Oslo local
    date), so weekend news isn't missed."""
    from zoneinfo import ZoneInfo
    local_weekday = now_utc.astimezone(ZoneInfo("Europe/Oslo")).weekday()
    days_back = 2 if local_weekday == 0 else 1  # Monday -> covers Sat+Sun+today
    return now_utc - timedelta(days=days_back)


def is_recent_enough(published_raw, cutoff: datetime) -> bool:
    if not published_raw:
        # Unknown publish date (HTML-scrape fallback) -- let dedup state be
        # the safety net instead of dropping it here.
        return True
    try:
        dt = dateparser.parse(published_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except (ValueError, OverflowError):
        return True


def collect_candidates(companies, cutoff, seen_ids):
    candidates = []
    for company in companies:
        if company.get("newsweb_issuer"):
            items = fetch_issuer_messages(company["newsweb_issuer"])
        else:
            items = fetch_company_news(company["id"], company.get("ir_url"))

        for item in items:
            if not is_recent_enough(item.get("published"), cutoff):
                continue
            iid = item_id(item["url"], item["title"])
            if iid in seen_ids:
                continue
            item["company"] = company["name"]
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

    if not should_run_now(now):
        print("[main] outside of the 4 target Oslo-time slots, skipping (DST-safe no-op)")
        return

    cutoff = lookback_cutoff(now)

    companies = load_companies()
    seen_ids = load_seen()

    candidates = collect_candidates(companies, cutoff, seen_ids)
    print(f"[main] {len(candidates)} candidate items after recency+dedup filtering")

    if not candidates:
        print("[main] nothing new, skipping email")
        return

    entries = draft_entries(candidates)
    print(f"[main] {len(entries)} entries kept after relevance filtering")

    if entries:
        html = render_html(entries)
        subject = f"Early Bird utkast -- {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        send_digest(subject, html)

    # Mark every fetched candidate (not just the ones the model kept) as
    # seen, so irrelevant items don't get re-evaluated every run either.
    for c in candidates:
        seen_ids.add(c["_id"])
    save_seen(seen_ids)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[main] FATAL: {e}", file=sys.stderr)
        raise
