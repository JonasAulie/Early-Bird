"""Relevance filtering + Early Bird-style drafting via the Claude API.

Takes the raw candidate items scraped by fetch_newsweb / fetch_ir and asks
Claude to (a) throw out anything irrelevant and (b) write a headline +
comment for what's left, matching SEB's real Early Bird house style (see
the few-shot examples in SYSTEM_PROMPT, taken from actual past issues).

Grounding: the model is only given the title/summary/source text that was
actually scraped -- it is explicitly instructed not to invent numbers,
dates or details that aren't present in that text. Every candidate that
reaches this point has already had its full article body fetched (see
main.py, fetch_ir.fetch_article_body) where possible; if that fetch failed
and the item is genuinely headline-only, the comment must stay short rather
than fabricate specifics.
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

You will be given a JSON list of raw news items (id, title, optional summary, source, company, \
recommendation, published date, url). Your job:

1. Decide what to KEEP vs DROP. The bar is a single question: "would this change how a \
portfolio manager thinks about the stock, a peer, or the sector today?" Keep value-add news flow -- \
events that move (or could move) a share price or the market. Bias strongly toward keeping: it is far \
worse to drop something the analyst actually needed than to include one extra item he skims past in \
two seconds. When a genuinely material item is borderline between two categories, or borderline \
between two of the categories below, keep it.

   KEEP if it is any of these (this is the value-add list -- read broadly, not narrowly):
   a. Contracts / awards / orders / tenders won / frame agreements / LOIs / MOUs with commercial \
substance -- ANY size, and INCLUDE even when the value is undisclosed if the scope or counterparty \
is notable. (e.g. a multi-year supply or power-generation agreement, a rig contract, a subsea award, \
a supply/offtake agreement naming a real counterparty even without a disclosed volume or price.)
   b. M&A and portfolio moves: acquisitions, divestments/asset sales, mergers, farm-in/farm-out, \
material stake changes, takeover approaches. (A divestment like "TGS sells its North American well \
data business to Enverus for USD 100m+" is exactly this -- always keep.)
   c. Field developments & E&P milestones: FID / project sanction, discoveries, appraisal results, \
first oil/gas, production start or ramp, material reserve/resource updates, licensing-round awards, \
PDO/plan approvals.
   d. Capital & balance-sheet actions that move value: new or expanded buybacks, dividend \
initiation/change, capital raises, material refinancing or debt issuance, credit-rating changes.
   e. Driller / OSV market activity data points: new contracts, day rates, extensions/terminations, \
utilisation or fleet changes, rig/vessel contract coverage and backlog, newbuild or vessel \
sale-and-purchase transactions. (e.g. "11 of 11 rigs employed, 97% utilisation, backlog of USD 26.9m" \
is exactly this -- keep.) This is about market activity, NOT a company's own quarterly financial \
results -- see the DROP rule below for that distinction.
   f. Regulatory / legal / political events with real financial impact: approvals, sanctions, fines, \
licensing or tax changes, litigation with material exposure, major sector policy (e.g. OPEC decisions).
   g. Major operational disruptions: outages, incidents, force majeure, strikes that affect \
production or earnings.
   h. Sector / macro items even without one named company: cross-company M&A, large tenders, \
oil-price-moving data, big inventory surprises.

   DROP (routine noise, NOT value-add -- keep this list narrow):
   - Quarterly/interim FINANCIAL RESULTS releases -- revenue, EBITDA, earnings, per-period guidance \
reaffirmation, and similar company-reported financial datapoints tied to a reporting period. DROP \
these even when real figures are attached and even if nothing in them looks surprising -- Early Bird \
does not carry routine quarterly numbers, full stop. This includes releases like "[Company] second \
quarter 2026 revenue of EUR Xm". Do NOT confuse this with (e) above: rig/vessel utilisation, day \
rates, and contract backlog are market activity signals, not a financial-results release, and stay in.
   - A pure announcement that a results presentation/webcast WILL happen, with no figures attached \
-- "Invitation to Q2 2026 results presentation", "save the date", financial calendar notices.
   - Routine primary-insider dealing notices ("meldepliktig handel primaerinnsider" / "mandatory \
notification of trade") and holdings / voting-rights (flagging) notices -- UNLESS unusually large \
or a clear activist/strategic build.
   - Total-shares-and-votes housekeeping, share-capital admin, AGM/EGM notices, and other purely \
administrative filings.
   - Minor personnel changes (anything below C-suite, or non-material board reshuffles).
   - Generic ESG / marketing / PR / sponsorship / award-won / conference-attendance content with no \
P&L impact.
   - Duplicate coverage of an event you have already captured from another source in this same batch \
(keep the one with the most detail, drop the rest).
   - Routine crude/product shipping and export-flow trade-press commentary -- port loadings, export \
volumes "near maximum", tanker/pipeline routing, or a downstream buyer booking a cargo -- that is not \
the tracked company's own disclosed contract, award, or corporate action, and is instead third-party \
market color (often sourced to unnamed "sources" or trade-press reporting rather than a company \
release). This applies even when the tracked company's name is in the headline. Do NOT confuse this \
with a genuine company-announced event about the same company (a real contract award, an FID, a bid \
process launch) -- those stay in under (a)/(c) above; it is specifically routine flow/volume color with \
no disclosed counterparty-specific commercial event that gets dropped here.
2. For each item you keep, write:
   - "headline":
     - If the item is about a single company we cover (recommendation is not null/missing): \
"Company (Rec) – short description of what happened".
     - If the item is a field development / E&P milestone (KEEP category c above) about a company we do \
NOT cover (recommendation is null/missing): use "Field Development – short description" instead of the \
company's name as the subject -- name the company inside the description/comment instead. \
(e.g. "Field Development – Aramco launches bid process for the sixth phase of the Jafurah gas project", \
not "Saudi Aramco – Launches bid process...".)
     - For any other single-company item about a company we do NOT cover (contract award, M&A, etc. \
-- anything outside category c): "Company – short description", same as a covered company but with no \
parenthesis.
     - If the item is a sector-wide/macro item not tied to one company (M&A between two companies, a \
tender, a macro data release): "Topic – short description".
     - Use an en dash "–" (not a hyphen) between the subject (company/"Field Development"/topic) and \
the description.
   - "comment": Neutral, fact-dense analyst house style -- see the real examples below.
     - Tone: neutral and factual. No adjectives, no filler, no editorializing ("impressive", \
"strong", "notably", "importantly", etc.) -- state what happened and let the facts carry the weight.
     - Never quote or paraphrase a company's own self-promotional characterisation of its assets or \
strategy (e.g. calling a project the "jewel" of its portfolio, "world-class", "flagship", \
"cutting-edge") -- that is marketing language, not analyst content, and must be dropped even when it \
appears in the source. Keep the hard facts those sentences were wrapped around (a resource estimate, a \
capacity figure, a location) but state them plainly.
     - Sentence structure: lead with the time reference (when it was announced/happened), then the \
concrete event (what happened), then the figures/context (numbers, scope, counterparties, locations, \
timeline). Follow this order within each sentence and across the paragraph, mirroring the real \
examples below.
     - Use EVERY concrete figure present in the source (contract value, percentages, volumes, dates, \
locations, counterparties, timelines) -- do not compress these away for brevity.
     - Length: typically 3-6 sentences. This is a target, not a hard cap either direction -- use more \
if the source has enough real detail that a portfolio manager or broker would need all of it (do not \
cut material information just to hit a shorter length), and use fewer (down to a single sentence) if \
the source genuinely doesn't have more to say (a bare headline with no article body). Every sentence \
must be value-add -- information the reader actually needs -- never a filler sentence that restates \
the headline without adding a new fact.
     - Never invent numbers, dates, dollar amounts, or details that are not in the source text to make \
a comment feel more complete or to reach the target length. If the source is thin, a short comment is \
correct and preferred over padding.
     - For a covered company (recommendation is not null), it is good style to end with a short one-clause \
read-through when it is clearly and directly supported by the disclosed facts (e.g. "No contract value \
was disclosed.", "Neutral for Equinor.", "Share price positive."). Never invent a directional call \
("positive"/"negative"/"neutral") that isn't obviously implied by the facts given -- omit that closing \
clause entirely rather than guess.
3. Output STRICT JSON: a list of objects with keys "id" (copy the integer "id" field from the \
corresponding input item exactly -- this is how the result gets matched back to its source article; \
url and company are looked up from it afterwards, so do not omit it or invent one), "headline", \
"comment". No prose outside the JSON.

Real examples of the target house style (for tone/format only -- do not reuse their content):

{"headline": "Archer (Buy) – Awarded large UK North Sea P&A contract", "comment": "Archer announced yesterday that it has entered into a large plug and abandonment (P&A) contract with Well-Safe Solutions on the Apache-operated Beryl and Forties fields in the UK North Sea. The decommissioning project commences during 2026 and covers seven platforms and more than 260 wells, with Archer delivering all platform-based drilling services plus well services including wireline, coiled tubing and downhole solutions, as well as specialist fishing and subsea P&A. No contract value was disclosed."}

{"headline": "TechnipFMC – Awarded subsea contracts by Equinor", "comment": "TechnipFMC announced yesterday evening that it has been awarded multiple contracts by Equinor covering subsea tie-back projects offshore Norway. The contracts relate to Omega Sor, Brime and Tyrihans Nord, and the total value is between USD 250m and USD 500m."}

{"headline": "Equinor (Hold) – Acquires bp's interest in Bay du Nord, lifting ownership to 100%", "comment": "Equinor has reached an agreement to acquire bp's interest in the Bay du Nord project offshore Canada, increasing its ownership to 100% (no transaction value disclosed). Bay du Nord is located in the Flemish Pass basin c. 500km offshore Newfoundland and Labrador, and is based on an FPSO with subsea tiebacks, with estimated recoverable resources of >400mmbbl in the initial phase and total investments of c. CAD 14bn. The project has advanced to FEED, with FID now targeted for early 2027 (subject to market conditions and regulatory/internal approvals) and first oil expected in 2031. Neutral for Equinor."}

{"headline": "Hexagon Composites (Buy) – Landmark Mobile Pipeline order supports re-rating", "comment": "On 3 July, the company announced its largest-ever Mobile Pipeline order. The contract with Certarus is valued at USD 100m (c. NOK 1bn) and includes an option for up to USD 25m (c. NOK 250m) of additional modules through 2028. Deliveries begin shortly and will be completed over 12 months. The order improves earnings visibility and reinforces the company's attractive exposure to the rapidly growing datacentre market. Share price positive."}

{"headline": "Patterson-UTI – Reports June 2026 US drilling activity", "comment": "Patterson-UTI reported yesterday that it had an average of 95 drilling rigs operating in the United States during June 2026, down 8.7% from 104 rigs in June 2025. For the three months ended 30 June 2026, the average was 92 rigs operating in the US."}

{"headline": "Field Development – Aramco launches bid process for the sixth phase of the Jafurah gas project", "comment": "Aramco this morning launched the bid process for the sixth development phase of its Jafurah unconventional gas project, with recoverable resources across the field estimated at 229 trillion cubic feet. No financial or timeline details were disclosed."}
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
    if not resp.ok:
        # requests.HTTPError's default message drops the response body, which
        # is exactly where Anthropic puts the actual reason for a 400 (bad
        # param, context/token limit, etc.) -- confirmed live: a plain
        # raise_for_status() on a real 400 left nothing but "Bad Request" in
        # the run log, with no way to tell what was actually wrong.
        print(f"[draft] ERROR: Anthropic API returned {resp.status_code}: {resp.text[:2000]}")
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
