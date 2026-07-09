"""Sends the finished digest via the Resend API.

Requires RESEND_API_KEY as an env var (set as a GitHub Actions secret --
see .github/workflows/early-bird.yml). Without a verified sending domain in
Resend (https://resend.com/domains), Resend restricts the shared sandbox
sender (onboarding@resend.dev) to delivering only to the account owner's own
signup address -- so for now this only sends to jonasaulie@gmail.com.
Confirmed live: adding jonas.aulie@seb.no gets a 403 from Resend ("You can
only send testing emails to your own email address"). To add it back,
verify a domain you actually control (not seb.no -- that needs SEB's own
IT/DNS admins) and set it as FROM_EMAIL.
"""
import os
from typing import List

import requests

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_RECIPIENTS = ["jonasaulie@gmail.com"]


def send_digest(subject: str, html_body: str, recipients: List[str] = None):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not set")
    # `or` (not just .get(default=)) matters here: GitHub Actions sets the env
    # var to an empty string when the secret doesn't exist, rather than
    # omitting it, so a plain default= would never kick in.
    from_email = os.environ.get("FROM_EMAIL") or "onboarding@resend.dev"
    recipients = recipients or DEFAULT_RECIPIENTS

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": from_email,
            "to": recipients,
            "subject": subject,
            "html": html_body,
        },
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"[emailer] ERROR {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()
