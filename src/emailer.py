"""Sends the finished digest via the Resend API.

Requires RESEND_API_KEY as an env var (set as a GitHub Actions secret --
see .github/workflows/early-bird.yml). FROM_EMAIL should be an address on a
domain you've verified in Resend (https://resend.com/domains); until a
domain is verified, Resend only lets you send to the account owner's own
address, which won't work for the jonas.aulie@seb.no recipient.
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
    from_email = os.environ.get("FROM_EMAIL", "early-bird@resend.dev")
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
