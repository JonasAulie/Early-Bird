"""One-off verification for three changes made together:

  1. fetch_ir.fetch_article_body() -- IR-scrape candidates only ever carried
     a bare headline before; this fetches the real press-release body so
     the drafter has enough grounding for a proper 3-6 sentence comment.
  2. draft.py's tightened SYSTEM_PROMPT (neutral/fact-dense tone, time ->
     event -> figures sentence order, 3-6 sentence target).
  3. emailer.send_digest()'s per-recipient sending (jonasaulie@gmail.com +
     jonas.aulie@seb.no as independent Resend calls).

Bypasses main.py's seen-state dedup entirely (today's real items are
already marked seen from earlier runs) so this exercises the new code
directly against a real, currently-live Baker Hughes headline instead of
finding zero new candidates.

Run via a throwaway workflow_dispatch job on a runner with real network +
secrets access.
"""
from src.fetch_ir import fetch_company_news, fetch_article_body
from src.draft import draft_entries
from src.emailer import send_digest
from src.watchlist import load_companies


def main():
    companies = {c["id"]: c for c in load_companies()}
    bakerhughes = companies["bakerhughes"]

    items = fetch_company_news(bakerhughes["id"], bakerhughes["ir_url"])
    dated = [it for it in items if it.get("published")]
    print(f"fetched {len(items)} items, {len(dated)} dated")
    if not dated:
        print("no dated items found, nothing to test against")
        return

    candidate = dated[0]
    print(f"\ntesting against: {candidate['title']!r}")
    print(f"url: {candidate['url']}")
    print(f"summary before fetch_article_body: {candidate.get('summary')!r}")

    body = fetch_article_body(candidate["url"], label="bakerhughes")
    print(f"\nfetched article body ({len(body) if body else 0} chars):")
    print(body[:1500] if body else "(None -- fetch failed)")

    candidate["summary"] = body
    candidate["company"] = bakerhughes["name"]
    candidate["recommendation"] = bakerhughes.get("recommendation")

    entries = draft_entries([candidate])
    print(f"\ndraft_entries returned {len(entries)} entries")
    for e in entries:
        print(f"\nheadline: {e.get('headline')}")
        comment = e.get("comment", "")
        sentence_count = comment.count(". ") + (1 if comment else 0)
        print(f"comment ({len(comment)} chars, ~{sentence_count} sentences): {comment}")

    if entries:
        e = entries[0]
        html = f'<p><b>{e["headline"]}</b><br/>{e["comment"]} <a href="{e["url"]}">[kilde]</a></p>'
        subject = "Early Bird TEST -- article body + two-recipient check (safe to ignore)"
        print(f"\nsending test email with subject: {subject!r}")
        results = send_digest(subject, html)
        print(f"send_digest returned {len(results)} successful result(s) "
              f"(out of {len(['jonasaulie@gmail.com', 'jonas.aulie@seb.no'])} attempted recipients)")


if __name__ == "__main__":
    main()
