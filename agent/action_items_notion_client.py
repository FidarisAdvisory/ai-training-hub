import os

# Notion database IDs
_FIDEL_PERSONAL_DB = "321d4ad6-3b6a-4515-b7bd-70156452c480"  # Action Items Tracker
_CEMEX_DB = "3a75a7fe-8de6-4c47-8634-19dafe18952a"           # CEMEX Action Items Tracker

# Status values that mean "open"
_PERSONAL_OPEN_STATUSES = {"Not started", "In progress"}
_CEMEX_OPEN_STATUSES = {"Not Started", "In Progress", "Blocked"}


def get_open_action_items() -> dict:
    """
    Fetch open action items from both Notion trackers.
    Returns {"mine": [...], "others": [...]}

    Each item: text, assignee, client, category, status, deadline, notes, url, source.

    Requires env var: NOTION_API_TOKEN
    """
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        print("Notion not configured (NOTION_API_TOKEN missing). Skipping Notion action items.")
        return {"mine": [], "others": []}

    try:
        from notion_client import Client
    except ImportError:
        print("notion-client not installed. Skipping Notion action items.")
        return {"mine": [], "others": []}

    client = Client(auth=token)
    mine: list[dict] = []
    others: list[dict] = []

    # ── Personal tracker (all items belong to Fidel) ──────────────────────────
    try:
        response = client.databases.query(
            database_id=_FIDEL_PERSONAL_DB,
            filter={
                "or": [
                    {"property": "Status", "status": {"equals": "Not started"}},
                    {"property": "Status", "status": {"equals": "In progress"}},
                ]
            },
            sorts=[{"property": "Deadline", "direction": "ascending"}],
        )
        for page in response.get("results", []):
            mine.append(_extract_personal_item(page))
    except Exception as e:
        print(f"Notion personal tracker query failed: {e}")

    # ── CEMEX tracker (split by owner) ────────────────────────────────────────
    try:
        response = client.databases.query(
            database_id=_CEMEX_DB,
            filter={
                "or": [
                    {"property": "Status", "status": {"equals": "Not Started"}},
                    {"property": "Status", "status": {"equals": "In Progress"}},
                    {"property": "Status", "status": {"equals": "Blocked"}},
                ]
            },
            sorts=[{"property": "Tower", "direction": "ascending"}],
        )
        for page in response.get("results", []):
            item = _extract_cemex_item(page)
            owner = item.get("assignee", "").lower()
            if "fidel" in owner or "salazar" in owner:
                mine.append(item)
            else:
                others.append(item)
    except Exception as e:
        print(f"Notion CEMEX tracker query failed: {e}")

    return {"mine": mine, "others": others}


def _extract_personal_item(page: dict) -> dict:
    props = page.get("properties", {})

    text = ""
    for prop in props.values():
        if prop.get("type") == "title":
            text = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            break

    status = _select_value(props.get("Status", {}), "status")
    client_val = _select_value(props.get("Client", {}), "select")
    category = _select_value(props.get("Category", {}), "select")
    deadline = _date_start(props.get("Deadline", {}))
    source_text = _rich_text_value(props.get("Source", {}))

    return {
        "text": text,
        "assignee": "Fidel Salazar",
        "client": client_val,
        "category": category,
        "status": status,
        "deadline": deadline,
        "notes": source_text,
        "url": page.get("url", ""),
        "source": "Notion — Action Items Tracker",
    }


def _extract_cemex_item(page: dict) -> dict:
    props = page.get("properties", {})

    text = ""
    for prop in props.values():
        if prop.get("type") == "title":
            text = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            break

    status = _select_value(props.get("Status", {}), "status")
    tower = _select_value(props.get("Tower", {}), "select")
    owner = _rich_text_value(props.get("Owner", {}))
    deadline = _date_start(props.get("Deadline", {}))
    notes = _rich_text_value(props.get("Notes / Follow-up Comments", {}))

    return {
        "text": text,
        "assignee": owner,
        "client": "CEMEX",
        "category": tower,
        "status": status,
        "deadline": deadline,
        "notes": notes,
        "url": page.get("url", ""),
        "source": "Notion — CEMEX Tracker",
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _select_value(prop: dict, prop_type: str) -> str:
    inner = prop.get(prop_type) or {}
    return inner.get("name", "")


def _rich_text_value(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


def _date_start(prop: dict) -> str:
    date_val = prop.get("date") or {}
    return date_val.get("start", "")
