"""
email_delivery.py — Send briefings via Postmark API.

Uses httpx (already installed) to send HTML emails via Postmark.
Set POSTMARK_API_TOKEN env var to enable real sending.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

POSTMARK_API_URL = "https://api.postmarkapp.com/email"


def send_briefing_email(
    to_email: str,
    subject: str,
    html_content: str,
    from_email: str | None = None,
    api_token: str | None = None,
) -> dict:
    """Send a single briefing email via Postmark.

    If POSTMARK_API_TOKEN is not set, logs the email as a stub.
    Returns a dict with status, message_id, etc.
    """
    token = api_token or os.environ.get("POSTMARK_API_TOKEN", "")
    sender = from_email or os.environ.get("POSTMARK_FROM_EMAIL", "briefing@example.com")

    if not token:
        logger.info("[EMAIL STUB] Would send to %s: %s (%d bytes)", to_email, subject, len(html_content))
        return {
            "status": "stubbed",
            "to": to_email,
            "subject": subject,
            "html_bytes": len(html_content),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        resp = httpx.post(
            POSTMARK_API_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": token,
            },
            json={
                "From": sender,
                "To": to_email,
                "Subject": subject,
                "HtmlBody": html_content,
                "MessageStream": "outbound",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("Email sent to %s: MessageID=%s", to_email, data.get("MessageID"))
        return {
            "status": "sent",
            "to": to_email,
            "subject": subject,
            "message_id": data.get("MessageID"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return {
            "status": "failed",
            "to": to_email,
            "subject": subject,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def send_all_briefings(
    audience_html: dict[str, str],
    date_str: str,
    audience_emails: dict[str, str] | None = None,
) -> list[dict]:
    """Send briefings to all audiences.

    audience_html: {audience_id: html_content}
    audience_emails: {audience_id: email_address} — defaults to config emails
    """
    from briefing.config import AUDIENCE_PROFILES

    if audience_emails is None:
        audience_emails = {aid: p["email"] for aid, p in AUDIENCE_PROFILES.items()}

    results = []
    for aud_id, html in audience_html.items():
        email = audience_emails.get(aud_id)
        if not email:
            logger.warning("No email for audience %s, skipping", aud_id)
            continue

        name = AUDIENCE_PROFILES.get(aud_id, {}).get("name", aud_id)
        subject = f"AI Weekly Briefing — {date_str}"

        result = send_briefing_email(
            to_email=email,
            subject=subject,
            html_content=html,
        )
        results.append(result)

    return results
