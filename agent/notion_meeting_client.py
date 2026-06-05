"""
Notion meeting notes client.

Reads recent Notion meeting pages and extracts action items from the content.

Required env var:
  NOTION_API_TOKEN    — Notion integration secret
  NOTION_MEETINGS_DB  — ID of the Meetings database (optional; falls back to
                        searching under NOTION_DATABASE_ID if not set)

The Notion meetings collection URL for Fidaris Advisory is:
  https://app.notion.com/p/c1e9cae0374049978086d3598f3d0f6a
So NOTION_MEETINGS_DB should be set to: c1e9cae0374049978086d3598f3d0f6a
"""

import datetime
import os
import re


def get_notion_meeting_action_items(days_back: int = 7) -> list[dict]:
    """
    Return a flat list of action items extracted from recent Notion meeting pages.

    Each item:
      {
        "meeting_title":  str,
        "meeting_date":   str (YYYY-MM-DD),
        "meeting_url":    str,
        "task":           str,
        "assignee":       str,
        "assignee_email": str,
      }
    """
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        print("  NOTION_API_TOKEN not set — skipping Notion meeting notes.")
        return []

    db_id = os.environ.get("NOTION_MEETINGS_DB") or os.environ.get("NOTION_DATABASE_ID")
    if not db_id:
        print("  NOTION_MEETINGS_DB not set — skipping Notion meeting notes.")
        return []

    try:
        from notion_client import Client
    except ImportError:
        print("  notion-client not installed — skipping Notion meeting notes.")
        return []

    client = Client(auth=token)

    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()

    # Query recent meeting pages (sorted by created_time desc)
    try:
        response = client.databases.query(
            database_id=db_id,
            filter={
                "property": "created_time",
                "date": {"on_or_after": cutoff},
            },
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            page_size=50,
        )
    except Exception as exc:
        # created_time filter may not be supported; fall back to last_edited_time
        try:
            response = client.databases.query(
                database_id=db_id,
                filter={
                    "property": "last_edited_time",
                    "date": {"on_or_after": cutoff},
                },
                sorts=[{"timestamp": "last_edited_time", "direction": "descending"}],
                page_size=50,
            )
        except Exception as exc2:
            print(f"  Notion meetings query failed: {exc2}")
            return []

    items: list[dict] = []
    for page in response.get("results", []):
        page_id = page["id"]
        page_url = page.get("url", "")
        meeting_title = _extract_title(page)
        meeting_date = _extract_date(page)

        action_items = _extract_action_items_from_page(client, page_id, meeting_title)
        for ai in action_items:
            ai["meeting_title"] = meeting_title
            ai["meeting_date"] = meeting_date
            ai["meeting_url"] = page_url
            items.append(ai)

    print(f"  Notion meetings: fetched {len(items)} action items from last {days_back} days.")
    return items


def _extract_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    return "Untitled Meeting"


def _extract_date(page: dict) -> str:
    created = page.get("created_time", "")
    return created[:10] if created else datetime.date.today().isoformat()


def _extract_action_items_from_page(client, page_id: str, meeting_title: str) -> list[dict]:
    """
    Retrieve block content from a Notion page and parse ACTION ITEMS section.
    Looks for checkbox blocks (to_do) or lines matching '- [ ] ...' patterns.
    Also parses the structured '### 4. ACTION ITEMS' section typical of AI-generated notes.
    """
    try:
        blocks_response = client.blocks.children.list(block_id=page_id, page_size=100)
    except Exception as exc:
        print(f"  Could not fetch blocks for '{meeting_title}': {exc}")
        return []

    blocks = blocks_response.get("results", [])
    items: list[dict] = []
    in_action_section = False

    for block in blocks:
        btype = block.get("type", "")

        # Detect the action items section header
        if btype in ("heading_2", "heading_3", "heading_1"):
            text = _block_text(block, btype)
            if re.search(r"action\s+items?", text, re.IGNORECASE):
                in_action_section = True
            elif in_action_section and re.match(r"^\d+\.", text.strip()):
                # Next numbered section — stop
                in_action_section = False
            continue

        if btype == "to_do":
            # Native Notion checkbox
            checked = block.get("to_do", {}).get("checked", False)
            if not checked:  # only unchecked = open items
                text = _block_text(block, btype)
                if text.strip():
                    assignee, task = _parse_assignee(text)
                    items.append({"task": task, "assignee": assignee, "assignee_email": ""})
            continue

        if in_action_section and btype in ("bulleted_list_item", "numbered_list_item", "paragraph"):
            text = _block_text(block, btype)
            # Match "- [ ] task text" or "• task — assigned to ..."
            if re.search(r"\[\s*[xX]\s*\]", text):
                continue  # completed
            text = re.sub(r"^\s*[-•]\s*\[\s*\]\s*", "", text).strip()
            if not text:
                continue
            assignee, task = _parse_assignee(text)
            items.append({"task": task, "assignee": assignee, "assignee_email": ""})

    return items


def _block_text(block: dict, btype: str) -> str:
    """Extract plain text from any Notion block type."""
    content = block.get(btype, {})
    rich_text = content.get("rich_text") or content.get("text") or []
    return "".join(r.get("plain_text", "") for r in rich_text)


def _parse_assignee(text: str) -> tuple[str, str]:
    """
    Try to extract 'assigned to NAME' from the end of a task string.
    Returns (assignee, cleaned_task).
    """
    patterns = [
        r"\s*[|\\]\s*(?:owner|assigned\s+to|assignee):\s*([^|\\]+?)(?:\s*[|\\].*)?$",
        r"\s*[-–]\s*assigned\s+to\s+([^|\\]+?)(?:\s*[|\\].*)?$",
        r"\s*\(assigned\s+to\s+([^)]+)\)\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            assignee = m.group(1).strip()
            task = text[: m.start()].strip()
            return assignee, task
    return "Unknown", text.strip()
