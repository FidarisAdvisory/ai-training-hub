import datetime
import os

import requests

FATHOM_BASE_URL = "https://api.fathom.ai/external/v1"


def _headers() -> dict:
    return {"X-Api-Key": os.environ["FATHOM_API_KEY"]}


def get_action_items(user_email: str, days_back: int = 30) -> dict:
    """
    Fetch meetings with action items from the last `days_back` days via Fathom REST API.
    Returns {"mine": [...], "others": [...]}

    Each item dict has: text, assignee, assignee_email, meeting_title, meeting_date,
    meeting_url, project (inferred from title keywords).

    Requires env var: FATHOM_API_KEY
    """
    if not os.environ.get("FATHOM_API_KEY"):
        print("Fathom not configured (FATHOM_API_KEY missing). Skipping.")
        return {"mine": [], "others": []}

    since = (
        datetime.date.today() - datetime.timedelta(days=days_back)
    ).isoformat() + "T00:00:00Z"

    params: dict = {
        "include_action_items": "true",
        "include_summary": "false",
        "created_after": since,
        "page_size": 100,
    }

    mine: list[dict] = []
    others: list[dict] = []

    while True:
        try:
            resp = requests.get(
                f"{FATHOM_BASE_URL}/meetings",
                headers=_headers(),
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Fathom API error: {e}")
            break

        data = resp.json()
        meetings = data.get("results", data.get("items", data if isinstance(data, list) else []))

        for meeting in meetings:
            action_items = meeting.get("action_items", [])
            if not action_items:
                continue

            meeting_title = meeting.get("title") or meeting.get("meeting_title") or "Untitled Meeting"
            raw_date = meeting.get("created_at") or meeting.get("recording_start_time") or ""
            meeting_date = raw_date[:10] if raw_date else ""
            meeting_url = meeting.get("url") or meeting.get("share_url") or ""
            project = _infer_project(meeting_title)

            for item in action_items:
                text = item.get("text") or item.get("action_item") or item.get("description") or ""
                assignee_name = (
                    item.get("assignee_name")
                    or item.get("assignee")
                    or item.get("assigned_to")
                    or ""
                )
                assignee_email = item.get("assignee_email") or item.get("email") or ""

                if not text:
                    continue

                entry = {
                    "text": text,
                    "assignee": assignee_name,
                    "assignee_email": assignee_email,
                    "meeting_title": meeting_title,
                    "meeting_date": meeting_date,
                    "meeting_url": meeting_url,
                    "project": project,
                    "source": "Fathom",
                }

                if _is_mine(assignee_name, assignee_email, user_email):
                    mine.append(entry)
                else:
                    others.append(entry)

        cursor = data.get("next_cursor") or data.get("cursor") if isinstance(data, dict) else None
        has_more = data.get("has_more", False) if isinstance(data, dict) else False
        if not cursor or not has_more:
            break
        params["cursor"] = cursor

    mine.sort(key=lambda x: x["meeting_date"], reverse=True)
    others.sort(key=lambda x: (x.get("assignee", ""), x["meeting_date"]), reverse=True)

    return {"mine": mine, "others": others}


def _is_mine(assignee_name: str, assignee_email: str, user_email: str) -> bool:
    name_lower = assignee_name.lower()
    email_lower = assignee_email.lower()
    return (
        "fidel" in name_lower
        or "salazar" in name_lower
        or user_email.lower() in email_lower
    )


def _infer_project(title: str) -> str:
    t = title.lower()
    if "cemex" in t or "p2p" in t or "o2c" in t or "r2r" in t or "readymix" in t or "rm " in t:
        return "CEMEX"
    if "highradius" in t or "cfp" in t or "friday" in t:
        return "CFP"
    if "deacero" in t or "de acero" in t:
        return "DEACERO"
    if (
        "training" in t
        or "entrenamiento" in t
        or "capacitaci" in t
        or "session" in t
        or "sesi" in t
        or "kevin" in t
        or "anthony" in t
        or "leonel" in t
        or "franco" in t
        or "valcourt" in t
        or "berhat" in t
    ):
        return "AI Trainings"
    if "fidaris" in t or "victor" in t or "syncron" in t or "o2c" in t:
        return "Fidaris"
    return "Other"
