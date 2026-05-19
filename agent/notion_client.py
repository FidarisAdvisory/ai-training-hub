import datetime
import os


def get_notion_tasks(today_date: str, tomorrow_date: str) -> dict:
    """
    Fetch tasks from a Notion database for today and tomorrow.
    Returns {"today": [...], "tomorrow": [...]} or empty lists if Notion is not configured.

    Expects these env vars:
      NOTION_API_TOKEN   - Notion integration secret
      NOTION_DATABASE_ID - ID of the tasks database
    The database must have a Date property (any name containing "date" or "due") and
    a Title property. Optionally: Status and Priority select/status properties.
    """
    token = os.environ.get("NOTION_API_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not token or not database_id:
        print("Notion not configured (NOTION_API_TOKEN or NOTION_DATABASE_ID missing). Skipping.")
        return {"today": [], "tomorrow": []}

    try:
        from notion_client import Client
    except ImportError:
        print("notion-client not installed. Skipping Notion tasks.")
        return {"today": [], "tomorrow": []}

    client = Client(auth=token)

    # Parse the date strings back into date objects for filtering
    today = datetime.datetime.strptime(today_date, "%A, %B %d, %Y").date()
    tomorrow = today + datetime.timedelta(days=1)

    today_iso = today.isoformat()
    tomorrow_iso = tomorrow.isoformat()

    # Query for tasks on today or tomorrow using an OR filter
    try:
        response = client.databases.query(
            database_id=database_id,
            filter={
                "or": [
                    {
                        "property": _find_date_property(client, database_id),
                        "date": {"equals": today_iso},
                    },
                    {
                        "property": _find_date_property(client, database_id),
                        "date": {"equals": tomorrow_iso},
                    },
                ]
            },
            sorts=[{"property": _find_date_property(client, database_id), "direction": "ascending"}],
        )
    except Exception as e:
        print(f"Notion query failed: {e}")
        return {"today": [], "tomorrow": []}

    today_tasks = []
    tomorrow_tasks = []

    for page in response.get("results", []):
        task = _extract_task(page)
        if task["due_date"] == today_iso:
            today_tasks.append(task)
        elif task["due_date"] == tomorrow_iso:
            tomorrow_tasks.append(task)

    return {"today": today_tasks, "tomorrow": tomorrow_tasks}


def _find_date_property(client, database_id: str) -> str:
    """Return the name of the first date-type property in the database."""
    db = client.databases.retrieve(database_id=database_id)
    for name, prop in db.get("properties", {}).items():
        if prop.get("type") == "date":
            return name
    # Fall back to common names
    for name in db.get("properties", {}):
        if "date" in name.lower() or "due" in name.lower():
            return name
    return "Date"


def _extract_task(page: dict) -> dict:
    props = page.get("properties", {})

    title = ""
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_parts)
            break

    due_date = ""
    status = ""
    priority = ""

    for name, prop in props.items():
        ptype = prop.get("type")
        if ptype == "date" and not due_date:
            date_val = prop.get("date") or {}
            due_date = date_val.get("start", "")
        elif ptype in ("status", "select") and "status" in name.lower():
            inner = prop.get(ptype) or {}
            status = inner.get("name", "")
        elif ptype == "select" and "priority" in name.lower():
            inner = prop.get("select") or {}
            priority = inner.get("name", "")

    return {
        "title": title,
        "status": status,
        "priority": priority,
        "due_date": due_date,
        "url": page.get("url", ""),
    }
