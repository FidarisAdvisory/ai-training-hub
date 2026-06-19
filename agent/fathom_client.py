"""
Fathom Video REST API client.

Requires env var: FATHOM_API_KEY
Generate one at: fathom.video/app/settings/api-tokens
"""
import datetime
import os

import requests

_API_BASE = "https://fathom.video/api/v1"
_TIMEOUT = 30


def _session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    return s


def get_meetings_with_action_items(api_key: str, days_back: int = 7) -> list[dict]:
    """
    Fetch all meetings from the past `days_back` days.
    Returns a list of meeting dicts; only meetings with action items are included.
    Each dict: {id, title, date, url, participants, action_items}
    Each action item: {text, assignee, clip_url}
    """
    since = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat() + "T00:00:00Z"
    session = _session(api_key)
    meetings = []
    params: dict = {"per_page": 50, "created_after": since}

    while True:
        resp = session.get(f"{_API_BASE}/calls", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        calls = body.get("calls") or body.get("data") or []
        for call in calls:
            items = _extract_action_items(call)
            if items:
                meetings.append({
                    "id": call.get("id") or call.get("recording_id"),
                    "title": call.get("title") or "Untitled Meeting",
                    "date": _parse_date(call),
                    "url": call.get("url") or call.get("recording_url") or "",
                    "participants": _parse_participants(call),
                    "action_items": items,
                })

        # Cursor-based pagination
        next_cursor = (
            body.get("next_cursor")
            or (body.get("meta") or {}).get("next_cursor")
            or (body.get("pagination") or {}).get("next_cursor")
            or (body.get("links") or {}).get("next")
        )
        if next_cursor:
            params = {"per_page": 50, "cursor": next_cursor}
        else:
            break

    # Sort newest first
    meetings.sort(key=lambda m: m["date"], reverse=True)
    return meetings


def _parse_date(call: dict) -> str:
    for field in ("started_at", "recorded_at", "created_at"):
        val = call.get(field) or ""
        if val:
            return val[:10]
    return ""


def _parse_participants(call: dict) -> list[str]:
    result = []
    for p in call.get("participants") or call.get("attendees") or []:
        if isinstance(p, dict):
            name = p.get("display_name") or p.get("name") or p.get("email") or ""
        else:
            name = str(p)
        if name:
            result.append(name)
    return result


def _extract_action_items(call: dict) -> list[dict]:
    raw = call.get("action_items") or []
    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("content") or item.get("description") or ""
        if not text:
            continue

        assignee_raw = item.get("assignee")
        if isinstance(assignee_raw, dict):
            assignee = (
                assignee_raw.get("display_name")
                or assignee_raw.get("name")
                or assignee_raw.get("email")
                or "Unassigned"
            )
        else:
            assignee = str(assignee_raw) if assignee_raw else "Unassigned"

        clip_url = item.get("url") or item.get("timestamp_url") or item.get("clip_url") or ""
        items.append({"text": text, "assignee": assignee, "clip_url": clip_url})
    return items
