"""Sends the finished digest via the Resend API.

Requires RESEND_API_KEY as an env var (set as a GitHub Actions secret --
see .github/workflows/early-bird.yml). Without a verified sending domain in
Resend (https://resend.com/domains), Resend restricts the shared sandbox
sender (onboarding@resend.dev) to delivering only to the account owner's own
signup address -- it will reject a request that also lists any other
recipient. jonas.aulie@seb.no cannot be verified as a *sending* domain here
(that needs SEB's own IT/DNS admins), but that's irrelevant to receiving --
any recipient address is fine once the FROM side is a verified domain. Until
a domain is verified, sending to jonas.aulie@seb.no will likely be rejected
by Resend.

To avoid that rejection silently blocking delivery to BOTH recipients, each
recipient gets its own independent API call below -- if SEB's address is
rejected, jonasaulie@gmail.com still gets the email, and the failure is
logged loudly rather than swallowed.
"""
import os
from typing import List

import requests

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_RECIPIENTS = ["jonasaulie@gmail.com", "jonas.aulie@seb.no"]


def send_digest(subject: str, html_body: str, recipients: List[str] = None):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not set")
    # `or` (not just .get(default=)) matters here: GitHub Actions sets the env
    # var to an empty string when the secret doesn't exist, rather than
    # omitting it, so a plain default= would never kick in.
    from_email = os.environ.get("FROM_EMAIL") or "onboarding@resend.dev"
    recipients = recipients or DEFAULT_RECIPIENTS

    results = []
    for recipient in recipients:
        resp = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [recipient],
                "subject": subject,
                "html": html_body,
            },
            timeout=30,
        )
        if resp.status_code >= 300:
            print(f"[emailer] ERROR {resp.status_code} sending to {recipient}: {resp.text}")
            continue
        results.append(resp.json())

    if not results:
        raise RuntimeError(f"failed to send digest to any of {recipients}")
    return results
