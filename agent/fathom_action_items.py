"""Fetch Fathom meeting emails from Gmail and extract their text bodies."""

import base64
import datetime
import re

from googleapiclient.discovery import build


def _build_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decode_part(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    """Recursively extract the best readable text from a MIME payload."""
    mime = payload.get("mimeType", "")

    # Direct text/plain
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_part(data) if data else ""

    parts = payload.get("parts", [])

    # Prefer plain text in parts
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return _decode_part(data)

    # Recurse into multipart containers
    for part in parts:
        text = _extract_body(part)
        if text:
            return text

    # Last resort: HTML (strip tags)
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            raw = _decode_part(data)
            return _strip_html(raw)

    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                          ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')]:
        text = text.replace(entity, char)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_fathom_meetings(credentials, days_back: int = 30) -> list[dict]:
    """
    Fetch Fathom meeting emails labeled 'Fathom' from the last `days_back` days.
    Returns a list of {title, date, body} dicts, newest first.
    """
    service = _build_service(credentials)
    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"label:Fathom after:{cutoff}"

    meetings: list[dict] = []
    try:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()
        messages = resp.get("messages", [])
        print(f"  Fathom: {len(messages)} email(s) labeled Fathom in last {days_back} days")

        for msg in messages:
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in data.get("payload", {}).get("headers", [])
            }
            subject = headers.get("Subject", "")
            date_str = headers.get("Date", "")
            body = _extract_body(data.get("payload", {}))

            if body and len(body.strip()) > 50:
                meetings.append({
                    "title": subject,
                    "date": date_str,
                    "body": body[:7000],
                })
    except Exception as e:
        print(f"  Fathom fetch error: {e}")

    return meetings
