"""
Fathom REST API client.

Fetches recent meetings and their action items.

Required env var:
  FATHOM_API_KEY  — your Fathom API token (Settings → API in the Fathom web app)
"""

import datetime
import os

import requests


_BASE_URL = "https://api.fathom.video/v1"


def get_fathom_action_items(days_back: int = 7) -> list[dict]:
    """
    Return a flat list of action items from Fathom meetings in the last `days_back` days.

    Each item:
      {
        "meeting_title": str,
        "meeting_date":  str (YYYY-MM-DD),
        "meeting_url":   str,
        "task":          str,
        "assignee":      str,
        "assignee_email": str,
      }
    """
    api_key = os.environ.get("FATHOM_API_KEY")
    if not api_key:
        print("  FATHOM_API_KEY not set — skipping Fathom data.")
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    cutoff = datetime.date.today() - datetime.timedelta(days=days_back)
    cutoff_iso = cutoff.isoformat() + "T00:00:00Z"

    items: list[dict] = []
    cursor: str | None = None

    while True:
        params: dict = {
            "page_size": 50,
            "created_after": cutoff_iso,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = requests.get(
                f"{_BASE_URL}/calls",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  Fathom API error: {exc}")
            break

        data = resp.json()
        calls = data.get("calls") or data.get("data") or data.get("results") or []

        for call in calls:
            meeting_date = _parse_date(call)
            meeting_title = call.get("title") or call.get("name") or "Untitled Meeting"
            meeting_url = call.get("url") or call.get("share_url") or ""

            # The API may embed action_items directly or require a sub-request
            action_items = call.get("action_items") or []
            if not action_items:
                call_id = call.get("id") or call.get("recording_id")
                if call_id:
                    action_items = _fetch_call_action_items(call_id, headers)

            for ai in action_items:
                task = ai.get("text") or ai.get("description") or str(ai)
                assignee = ai.get("assignee_name") or ai.get("assigned_to") or "Unknown"
                assignee_email = ai.get("assignee_email") or ""
                items.append({
                    "meeting_title": meeting_title,
                    "meeting_date": meeting_date,
                    "meeting_url": meeting_url,
                    "task": task,
                    "assignee": assignee,
                    "assignee_email": assignee_email,
                })

        cursor = data.get("next_cursor") or data.get("cursor")
        if not cursor:
            break

    print(f"  Fathom: fetched {len(items)} action items from last {days_back} days.")
    return items


def _fetch_call_action_items(call_id: str, headers: dict) -> list[dict]:
    """Fetch action items for a single call if not returned inline."""
    try:
        resp = requests.get(
            f"{_BASE_URL}/calls/{call_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("action_items") or []
    except requests.RequestException:
        return []


def _parse_date(call: dict) -> str:
    for field in ("recording_started_at", "started_at", "created_at", "date"):
        val = call.get(field)
        if val:
            return val[:10]  # YYYY-MM-DD
    return datetime.date.today().isoformat()
