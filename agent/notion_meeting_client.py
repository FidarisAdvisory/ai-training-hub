import datetime
import os
import re


def get_meeting_action_items(days_back: int = 7, user_name: str = "Fidel Salazar") -> dict:
    """
    Query the Notion meetings database for recent meeting notes and extract
    action items from page content (to-do / checkbox blocks).

    Returns:
        {
            "mine":   [{"task", "assignee", "meeting", "date", "url"}, ...],
            "others": [{"task", "assignee", "meeting", "date", "url"}, ...],
        }
    """
    token = os.environ.get("NOTION_API_TOKEN", "")
    meetings_db_id = os.environ.get("NOTION_MEETINGS_DB_ID", "")

    if not token or not meetings_db_id:
        print("Notion meetings not configured (NOTION_API_TOKEN or NOTION_MEETINGS_DB_ID missing). Skipping.")
        return {"mine": [], "others": []}

    try:
        from notion_client import Client
    except ImportError:
        print("notion-client not installed. Skipping Notion meeting notes.")
        return {"mine": [], "others": []}

    client = Client(auth=token)
    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()

    pages = _query_recent_pages(client, meetings_db_id, cutoff)
    print(f"  Notion meetings: {len(pages)} page(s) found in last {days_back} days")

    mine: list[dict] = []
    others: list[dict] = []

    for page in pages:
        title, date, url = _extract_page_meta(page)
        action_items = _fetch_page_action_items(client, page["id"])

        for item in action_items:
            assignee = item.get("assignee", "")
            entry = {
                "task": item["task"],
                "assignee": assignee,
                "meeting": title,
                "date": date,
                "url": url,
            }
            if user_name.lower() in assignee.lower() or not assignee:
                if user_name.lower() in assignee.lower():
                    mine.append(entry)
                else:
                    others.append(entry)
            else:
                others.append(entry)

    return {"mine": mine, "others": others}


def _query_recent_pages(client, db_id: str, cutoff: str) -> list[dict]:
    try:
        response = client.databases.query(
            database_id=db_id,
            filter={
                "property": "Created time",
                "date": {"on_or_after": cutoff},
            },
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            page_size=50,
        )
        return response.get("results", [])
    except Exception as e:
        print(f"  Notion meetings query failed: {e}")
        return []


def _extract_page_meta(page: dict) -> tuple[str, str, str]:
    props = page.get("properties", {})

    title = ""
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            title = "".join(p.get("plain_text", "") for p in parts).strip()
            break
    if not title:
        title = "Meeting"

    created = page.get("created_time", "")
    date = created[:10] if created else ""
    url = page.get("url", "")

    return title, date, url


def _fetch_page_action_items(client, page_id: str) -> list[dict]:
    """Walk all blocks in a page and extract to-do blocks + lines matching 'assigned to X'."""
    items: list[dict] = []
    try:
        blocks_resp = client.blocks.children.list(block_id=page_id, page_size=100)
    except Exception:
        return items

    for block in blocks_resp.get("results", []):
        block_type = block.get("type", "")

        # Standard to-do checkbox blocks
        if block_type == "to_do":
            texts = block.get("to_do", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts).strip()
            if text:
                assignee = _extract_assignee(text)
                task = _strip_assignee(text)
                items.append({"task": task, "assignee": assignee})

        # Bulleted/numbered list items that mention action items
        elif block_type in ("bulleted_list_item", "numbered_list_item", "paragraph"):
            inner = block.get(block_type, {})
            texts = inner.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in texts).strip()
            # Only capture lines that look like assigned action items
            if "assigned to" in text.lower() or (text.startswith("[ ]") or text.startswith("- [ ]")):
                assignee = _extract_assignee(text)
                task = _strip_assignee(text).lstrip("-[ ]").strip()
                if task:
                    items.append({"task": task, "assignee": assignee})

    return items


def _extract_assignee(text: str) -> str:
    m = re.search(r"(?:assigned to|—\s*)([^(]+?)(?:\s*\(|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip(" —")
    return ""


def _strip_assignee(text: str) -> str:
    text = re.sub(r"\s*—\s*assigned to .+?(?:\s*\(https?://[^\)]+\))?$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(https?://[^\)]+\)$", "", text)
    return text.strip()
