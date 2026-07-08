"""Relevance filtering + Early Bird-style drafting via the Claude API.

Takes the raw candidate items scraped by fetch_newsweb / fetch_ir and asks
Claude to (a) throw out anything irrelevant and (b) write a headline + a
short (2-4 sentence) comment for what's left, in the same voice as SEB's
Early Bird sector notes.

Grounding: the model is only given the title/summary/source text that was
actually scraped -- it is explicitly instructed not to invent numbers,
dates or details that aren't present in that text. For headline-only items
(no summary), the comment must stay generic rather than fabricate specifics.
"""
import json
import os
from typing import List, Dict

import requests

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are drafting candidate entries for "Early Bird", a daily sector note an \
equity research analyst sends to institutional portfolio managers covering energy \
(oil, oilfield services, offshore drilling, and related renewables/maritime names).

You will be given a JSON list of raw news items (title, optional summary, source, company, \
recommendation, published date, url). Your job:

1. DROP anything that is not relevant. Relevant means:
   - It's about a company in the analyst's coverage universe or a major energy company, AND
   - It's a contract/award of meaningful size, a major sector event (M&A, regulatory, macro data \
release, large discovery/development decision, big personnel/strategy news), or something else a \
portfolio manager would consider a genuine value-add to know about before the market opens.
   - Routine/trivial items (minor personnel changes, generic ESG fluff, small immaterial contracts, \
duplicate coverage of the same event) should be dropped.
2. For each item you keep, write:
   - "headline":
     - If the item is about a single company: "Company (Rec) – short description of what happened", \
e.g. "Equinor (Hold) – Q2 trading update shows lower price achievement than we had expected". Use the \
"recommendation" field given in the input verbatim as Rec. If "recommendation" is null/missing (we \
don't cover that company), DROP the parenthesis entirely: "ExxonMobil – Announces $2bn buyback".
     - If the item is a sector-wide/macro item not tied to one company (e.g. M&A between two \
companies, a tender, a macro data release): "Topic – short description", e.g. "Offshore drilling – \
Constellation rig Amaralina Star approved in Brazil".
     - Use an en dash "–" (not a hyphen) between the company/topic part and the description.
   - "comment": 1-3 short, factual sentences. Be strictly on-point -- give ONLY what a portfolio \
manager needs to know (the concrete fact: size, counterparty, timing, financial impact if stated) and \
nothing else. NO filler, throat-clearing, or restating the headline in different words. If there is \
genuinely nothing more to add beyond the headline, it is fine for the comment to be a single short \
sentence -- do not pad it out. State only facts present in the input title/summary -- DO NOT invent \
numbers, dates, dollar amounts, or details that are not in the source text.
3. Output STRICT JSON: a list of objects with keys "headline", "comment", "company", "url", \
"source_title" (the original title, for traceability). No prose outside the JSON.
"""


def draft_entries(candidate_items: List[Dict], api_key: str = None) -> List[Dict]:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    if not candidate_items:
        return []

    user_content = json.dumps(candidate_items, ensure_ascii=False, indent=2)

    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=180,
    )
    resp.raise_for_status()
    payload = resp.json()
    text = "".join(block.get("text", "") for block in payload.get("content", []))
    truncated = payload.get("stop_reason") == "max_tokens"
    return _parse_json_response(text, truncated)


def _parse_json_response(text: str, truncated: bool = False) -> List[Dict]:
    text = text.strip()
    # Be tolerant of the model wrapping the JSON in a code fence.
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        pass

    if truncated:
        # Hit max_tokens mid-array. Salvage whatever complete objects came
        # before the cut-off rather than throwing away good entries -- trim
        # back to the last complete object and close the array ourselves.
        last_complete = text.rfind("},")
        if last_complete != -1:
            salvaged = text[: last_complete + 1] + "]"
            try:
                parsed = json.loads(salvaged)
                if isinstance(parsed, list):
                    print(f"[draft] WARNING: response hit max_tokens; salvaged {len(parsed)} "
                          f"complete entries from the truncated output")
                    return parsed
            except json.JSONDecodeError:
                pass

    print("[draft] WARNING: could not parse model response as JSON, dropping this batch")
    print(text[:2000])
    return []
