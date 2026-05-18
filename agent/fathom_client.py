import datetime
import os

import requests

FATHOM_BASE = "https://fathom.video/api/v1"


def get_action_items(days_back: int = 7, user_email: str = "", user_name: str = "Fidel Salazar") -> dict:
    """
    Fetch recent Fathom meetings and split action items into mine vs. others.

    Returns:
        {
            "mine":   [{"task", "assignee", "meeting", "date", "url"}, ...],
            "others": [{"task", "assignee", "meeting", "date", "url"}, ...],
        }
    """
    api_key = os.environ.get("FATHOM_API_KEY", "")
    if not api_key:
        print("FATHOM_API_KEY not set. Skipping Fathom.")
        return {"mine": [], "others": []}

    if not user_email:
        user_email = os.environ.get("USER_EMAIL", "")

    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days_back)).isoformat() + "Z"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    meetings = _fetch_all_meetings(headers, cutoff)
    print(f"  Fathom: {len(meetings)} meeting(s) found in last {days_back} days")
    return _split_action_items(meetings, user_email.lower(), user_name.lower())


def _fetch_all_meetings(headers: dict, created_after: str) -> list[dict]:
    meetings: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "created_after": created_after,
            "include_action_items": "true",
            "include_summary": "true",
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = requests.get(
                f"{FATHOM_BASE}/calls",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Fathom API error: {e}")
            break

        data = resp.json()

        # Fathom may return a list or a dict with a "calls" / "recordings" key
        if isinstance(data, list):
            meetings.extend(data)
            break
        elif isinstance(data, dict):
            for key in ("calls", "recordings", "data"):
                if key in data and isinstance(data[key], list):
                    meetings.extend(data[key])
                    break
            cursor = data.get("next_cursor") or data.get("cursor")
            if not cursor:
                break
        else:
            break

    return meetings


def _split_action_items(meetings: list[dict], user_email: str, user_name: str) -> dict:
    mine: list[dict] = []
    others: list[dict] = []

    for mtg in meetings:
        title = mtg.get("title") or mtg.get("summary") or "Unknown Meeting"
        raw_date = mtg.get("recorded_at") or mtg.get("created_at") or mtg.get("date") or ""
        date = raw_date[:10] if raw_date else ""
        mtg_url = mtg.get("url") or mtg.get("share_url") or ""

        for item in mtg.get("action_items", []):
            assignee = item.get("assignee") or item.get("assigned_to") or ""
            task = item.get("text") or item.get("action") or item.get("description") or ""
            item_url = item.get("url") or mtg_url

            entry = {
                "task": task.strip(),
                "assignee": assignee.strip(),
                "meeting": title.strip(),
                "date": date,
                "url": item_url,
            }

            assignee_lower = assignee.lower()
            if user_email in assignee_lower or user_name in assignee_lower:
                mine.append(entry)
            else:
                others.append(entry)

    mine.sort(key=lambda x: x["date"], reverse=True)
    others.sort(key=lambda x: x["date"], reverse=True)
    return {"mine": mine, "others": others}
