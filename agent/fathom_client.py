import datetime
import os
from typing import Optional

import requests

FATHOM_API_BASE = os.environ.get("FATHOM_API_BASE", "https://api.fathom.video/v2")
FATHOM_OWNER_NAME = os.environ.get("FATHOM_OWNER_NAME", "Fidel Salazar")


def _headers() -> dict:
    api_key = os.environ["FATHOM_API_KEY"]
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _parse_action_items(raw: list) -> list[dict]:
    """Normalise action item objects from Fathom API response."""
    items = []
    for ai in raw:
        # Different Fathom API versions may use different field names
        text = ai.get("text") or ai.get("title") or ai.get("description") or ""
        assignee = (
            ai.get("assignee_name")
            or ai.get("assigned_to")
            or ai.get("assignee", {}).get("name", "")
            if isinstance(ai.get("assignee"), dict)
            else ai.get("assignee", "")
        )
        completed = ai.get("completed", False) or ai.get("is_completed", False)
        timestamp_url = ai.get("timestamp_url") or ai.get("deep_link") or ""
        items.append(
            {
                "text": text.strip(),
                "assignee": (assignee or "").strip(),
                "completed": bool(completed),
                "timestamp_url": timestamp_url,
            }
        )
    return [i for i in items if i["text"]]


def get_recordings_with_action_items(
    days_back: int = 30,
    max_recordings: int = 100,
) -> list[dict]:
    """
    Fetch Fathom recordings from the last `days_back` days, including action items.
    Returns a list of dicts: {title, date, url, recorded_by, attendees, action_items}.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()

    recordings = []
    cursor = None

    while len(recordings) < max_recordings:
        params: dict = {
            "limit": min(50, max_recordings - len(recordings)),
            "order": "desc",
            "include_action_items": "true",
            "created_after": f"{cutoff}T00:00:00Z",
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = requests.get(
                f"{FATHOM_API_BASE}/recordings",
                headers=_headers(),
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Fathom API error: {e}")
            break

        data = resp.json()
        page = data.get("data") or data.get("recordings") or data.get("results") or []
        if not page:
            break

        for rec in page:
            date_str = (
                rec.get("recorded_at")
                or rec.get("started_at")
                or rec.get("created_at")
                or ""
            )[:10]

            raw_ais = (
                rec.get("action_items")
                or rec.get("actionItems")
                or []
            )
            action_items = _parse_action_items(raw_ais)

            attendees = []
            for inv in rec.get("calendar_invitees") or rec.get("attendees") or []:
                if isinstance(inv, str):
                    attendees.append(inv)
                elif isinstance(inv, dict):
                    attendees.append(inv.get("email") or inv.get("name") or "")

            recorded_by = (
                rec.get("recorded_by")
                or rec.get("host_name")
                or rec.get("owner", {}).get("name", "")
                if isinstance(rec.get("owner"), dict)
                else rec.get("owner", "")
            )

            recordings.append(
                {
                    "recording_id": rec.get("id") or rec.get("recording_id"),
                    "title": rec.get("title") or rec.get("name") or "(Untitled)",
                    "date": date_str,
                    "url": rec.get("url") or rec.get("share_url") or "",
                    "recorded_by": recorded_by,
                    "attendees": [a for a in attendees if a],
                    "action_items": action_items,
                }
            )

        cursor = data.get("next_cursor") or data.get("cursor") or data.get("next")
        if not cursor:
            break

    return recordings


def split_action_items(
    recordings: list[dict],
    owner_name: Optional[str] = None,
) -> tuple[list[dict], list[dict]]:
    """
    Split action items into (mine, others).
    Each returned item is: {text, assignee, meeting_title, meeting_date, meeting_url, completed}.
    """
    owner = (owner_name or FATHOM_OWNER_NAME).lower()
    mine = []
    others = []

    for rec in recordings:
        ctx = {
            "meeting_title": rec["title"],
            "meeting_date": rec["date"],
            "meeting_url": rec["url"],
        }
        for ai in rec["action_items"]:
            if ai["completed"]:
                continue
            entry = {**ctx, **ai}
            assignee = ai["assignee"].lower()
            # Match owner name loosely: first or last name is sufficient
            owner_parts = owner.split()
            is_mine = any(part in assignee for part in owner_parts) or not assignee
            if is_mine:
                mine.append(entry)
            else:
                others.append(entry)

    return mine, others
