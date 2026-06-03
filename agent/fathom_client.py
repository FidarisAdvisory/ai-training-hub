"""
Fetch today's Fathom meeting summaries from Gmail.

Fathom sends a formatted email after each recorded meeting (label: Fathom).
This module pulls those emails from today and returns structured records.
"""
import base64
import datetime
import os
import re

from googleapiclient.discovery import build


def _build_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decode_body(payload) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    parts = []
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            parts.append(base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore"))
    for part in payload.get("parts", []):
        parts.extend([_decode_body(part)])
    return "\n".join(p for p in parts if p)


def _extract_action_block(body: str) -> str:
    """
    Try to isolate the action-item section of the Fathom email body.
    Falls back to the full body so Claude can always find items.
    """
    patterns = [
        r"(?:action items?|next steps?|to[- ]dos?)[:\n]+(.+?)(?:\n\n|\Z)",
        r"(?:## action items?|## next steps?)(.+?)(?:\n##|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0)[:3000]
    return body[:4000]


def get_todays_fathom_meetings(credentials, days_back: int = 1) -> list[dict]:
    """
    Return a list of Fathom meeting records from the past `days_back` days.

    Each record has:
      - subject: email subject (usually the meeting title)
      - date: email date header string
      - body: extracted text content (action items section preferred)
    """
    service = _build_service(credentials)
    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"label:Fathom after:{cutoff}"

    try:
        resp = service.users().messages().list(userId="me", q=query, maxResults=30).execute()
    except Exception as e:
        print(f"  Fathom Gmail fetch error: {e}")
        return []

    meetings = []
    for msg in resp.get("messages", []):
        try:
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in data.get("payload", {}).get("headers", [])
            }
            body = _decode_body(data.get("payload", {}))
            meetings.append({
                "subject": headers.get("Subject", "(untitled)"),
                "date": headers.get("Date", ""),
                "body": _extract_action_block(body),
            })
        except Exception as e:
            print(f"  Could not fetch Fathom message {msg['id']}: {e}")

    print(f"  Fathom: {len(meetings)} meeting email(s) found for the past {days_back} day(s)")
    return meetings
