#!/usr/bin/env python3
"""
Daily Action Items Digest
Pulls action items from Fathom meetings and Notion meeting notes,
categorizes them (assigned to me vs. others), and sends a formatted email.

Required environment variables:
  NOTION_TOKEN         - Notion integration token (from notion.so/my-integrations)
  NOTION_MEETINGS_DB   - Notion meetings database/collection ID
                         (default: 2f31df44-77bc-4bb5-88f9-b452f7196f48)
  FATHOM_API_TOKEN     - Fathom API token (from fathom.video/settings/api)
  GMAIL_USER           - Gmail address used to send the email
  GMAIL_APP_PASSWORD   - Gmail App Password (not your main password)
  RECIPIENT_EMAIL      - Destination email (defaults to GMAIL_USER)
  MY_NAME              - Your full name as it appears in meeting notes
  MY_EMAIL             - Your email for matching Fathom assignments
  LOOKBACK_DAYS        - How many days back to scan (default: 1)
"""

import os
import re
import json
import smtplib
import textwrap
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_MEETINGS_DB = os.environ.get(
    "NOTION_MEETINGS_DB", "2f31df44-77bc-4bb5-88f9-b452f7196f48"
)
FATHOM_API_TOKEN = os.environ.get("FATHOM_API_TOKEN", "")
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)
MY_NAME = os.environ.get("MY_NAME", "Fidel Salazar")
MY_EMAIL = os.environ.get("MY_EMAIL", GMAIL_USER)
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "1"))

NOTION_BASE = "https://api.notion.com/v1"
FATHOM_BASE = "https://api.fathom.video/v1"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
FATHOM_HEADERS = {
    "Authorization": f"Bearer {FATHOM_API_TOKEN}",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ActionItem:
    def __init__(self, text: str, assignee: str, project: str,
                 deadline: str, owner: str, source: str):
        self.text = text.strip()
        self.assignee = assignee.strip()
        self.project = project.strip()
        self.deadline = deadline.strip()
        self.owner = owner  # "me" or "other"
        self.source = source  # meeting title or Fathom call title

    def is_mine(self) -> bool:
        return self.owner == "me"


# ---------------------------------------------------------------------------
# Notion helpers
# ---------------------------------------------------------------------------

def notion_get(path: str, **kwargs) -> dict:
    resp = requests.get(f"{NOTION_BASE}/{path}", headers=NOTION_HEADERS, **kwargs)
    resp.raise_for_status()
    return resp.json()


def notion_post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{NOTION_BASE}/{path}", headers=NOTION_HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_recent_notion_meetings(since: datetime) -> list[dict]:
    """Query the Meetings database for pages edited after `since`."""
    filter_payload = {
        "filter": {
            "timestamp": "last_edited_time",
            "last_edited_time": {
                "on_or_after": since.isoformat(),
            },
        },
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        "page_size": 100,
    }
    data = notion_post(f"databases/{NOTION_MEETINGS_DB}/query", filter_payload)
    pages = data.get("results", [])
    # Paginate
    while data.get("has_more"):
        filter_payload["start_cursor"] = data["next_cursor"]
        data = notion_post(f"databases/{NOTION_MEETINGS_DB}/query", filter_payload)
        pages.extend(data.get("results", []))
    return pages


def get_page_text(page_id: str) -> str:
    """Retrieve all block content of a page as plain text."""
    blocks = []
    url = f"blocks/{page_id}/children"
    params = {"page_size": 100}
    while True:
        data = notion_get(url, params=params)
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]

    lines = []
    for block in blocks:
        text = extract_block_text(block)
        if text:
            lines.append(text)
    return "\n".join(lines)


def extract_block_text(block: dict) -> str:
    """Flatten a Notion block to plain text."""
    btype = block.get("type", "")
    content = block.get(btype, {})
    rich_texts = content.get("rich_text", [])
    text = "".join(rt.get("plain_text", "") for rt in rich_texts)
    prefix = ""
    if btype in ("bulleted_list_item", "to_do"):
        checked = content.get("checked", False)
        prefix = "- [x] " if checked else "- [ ] "
    elif btype == "heading_1":
        prefix = "# "
    elif btype in ("heading_2", "heading_3"):
        prefix = "## "
    return prefix + text if text else ""


def extract_meeting_title(page: dict) -> str:
    """Get a human-readable meeting title from a Notion page."""
    props = page.get("properties", {})
    for key in ("Name", "Title", "title"):
        prop = props.get(key, {})
        if prop.get("type") == "title":
            rich = prop.get("title", [])
            return "".join(r.get("plain_text", "") for r in rich)
    # Fallback: use page id
    return f"Meeting ({page.get('id', '')[:8]})"


def extract_action_items_from_text(text: str, source: str) -> list[ActionItem]:
    """
    Parse Notion meeting note text and extract structured action items.
    Looks for sections like:
      ### 4. ACTION ITEMS
      - [ ] Person to do X | project context | Deadline: ...
    """
    items: list[ActionItem] = []

    # Find the ACTION ITEMS section
    section_match = re.search(
        r"##\s*(?:\d+\.\s*)?ACTION ITEMS\b(.*?)(?=\n##\s|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not section_match:
        return items

    section = section_match.group(1)

    # Each action item line: - [ ] <text>
    for raw_line in re.findall(r"-\s*\[\s*[x ]?\s*\]\s*(.+)", section):
        # Strip footnote references like [^url]
        line = re.sub(r"\[\^[^\]]+\]", "", raw_line).strip()
        if not line:
            continue

        # Determine assignment
        owner, assignee = classify_assignee(line)

        # Extract project/context from pipe-separated parts
        parts = [p.strip() for p in line.split("|")]
        task_text = parts[0].strip()
        project = parts[1] if len(parts) > 1 else source
        deadline_raw = " ".join(parts[2:]) if len(parts) > 2 else "TBD"
        deadline = re.sub(r"(?i)deadline\s*:\s*", "", deadline_raw).strip() or "TBD"

        items.append(ActionItem(
            text=task_text,
            assignee=assignee,
            project=project,
            deadline=deadline,
            owner=owner,
            source=source,
        ))

    return items


def classify_assignee(line: str) -> tuple[str, str]:
    """Return ("me"|"other", assignee_name) for an action item line."""
    # Common first-person patterns: "Fidel to ...", "I will ...", "[Fidel] ..."
    line_lower = line.lower()
    my_first = MY_NAME.split()[0].lower()
    my_last = MY_NAME.split()[-1].lower()

    if re.match(rf"^{my_first}\b", line_lower) or re.match(rf"^{my_last}\b", line_lower):
        return ("me", MY_NAME)

    # Look for bold/named patterns like **Person** or "Person to" or "Person —"
    name_match = re.match(r"^\*?\*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\*?\*?\s*(?:to |—|–|:)", line)
    if name_match:
        candidate = name_match.group(1)
        if candidate.lower().startswith(my_first) or candidate.lower().endswith(my_last):
            return ("me", MY_NAME)
        return ("other", candidate)

    # Check for Fernando/Fidel shared items
    if re.search(rf"\b{my_first}\b", line_lower) and re.search(r"\bfernando\b", line_lower):
        return ("me", f"{MY_NAME} / Fernando")

    if re.search(rf"\b{my_first}\b", line_lower):
        return ("me", MY_NAME)

    return ("other", "")


# ---------------------------------------------------------------------------
# Fathom helpers
# ---------------------------------------------------------------------------

def get_fathom_action_items(since: datetime) -> list[ActionItem]:
    """Pull recent Fathom meetings and extract their action items."""
    if not FATHOM_API_TOKEN:
        return []

    items: list[ActionItem] = []
    params = {
        "created_after": since.isoformat(),
        "include_action_items": "true",
        "page_size": 50,
    }
    try:
        resp = requests.get(f"{FATHOM_BASE}/calls", headers=FATHOM_HEADERS, params=params)
        resp.raise_for_status()
        calls = resp.json().get("results", [])
    except Exception:
        return []

    my_name_lower = MY_NAME.lower()
    my_email_lower = MY_EMAIL.lower()

    for call in calls:
        title = call.get("title", "Unknown Meeting")
        for ai in call.get("action_items", []):
            text = ai.get("text", "").strip()
            assignee = ai.get("assigned_to", "")
            if not text:
                continue
            if (assignee.lower() in my_name_lower or
                    my_email_lower in assignee.lower() or
                    my_name_lower in text.lower()):
                owner = "me"
            else:
                owner = "other"
            items.append(ActionItem(
                text=text,
                assignee=assignee or "Unknown",
                project=title,
                deadline=ai.get("due_date", "TBD") or "TBD",
                owner=owner,
                source=title,
            ))
    return items


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

def build_email_html(
    my_items: list[ActionItem],
    other_items: list[ActionItem],
    today: datetime,
) -> str:
    date_str = today.strftime("%A, %B %-d, %Y")

    def items_html(items: list[ActionItem]) -> str:
        if not items:
            return "<p style='color:#6b7280;font-style:italic;'>No action items found.</p>"

        # Group by project
        grouped: dict[str, list[ActionItem]] = {}
        for item in items:
            grouped.setdefault(item.project, []).append(item)

        html = ""
        for project, group in grouped.items():
            html += f"<h3>{project}</h3><ul>"
            for item in group:
                due_color = "#dc2626" if "today" in item.deadline.lower() else \
                            "#d97706" if any(w in item.deadline.lower()
                                             for w in ["tomorrow", "june 7", "june 8", "june 9", "june 10", "june 11"]) else \
                            "#6b7280"
                assignee_part = f" <span style='color:#4b5563;font-size:12px;'>({item.assignee})</span>" \
                                if item.assignee and item.assignee != MY_NAME else ""
                html += (
                    f"<li>{item.text}{assignee_part}"
                    f" &nbsp;<span style='font-size:11px;font-style:italic;color:{due_color};'>Due: {item.deadline}</span></li>"
                )
            html += "</ul>"
        return html

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #1a1a1a; max-width: 700px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #1a3c5e; font-size: 22px; border-bottom: 3px solid #1a3c5e; padding-bottom: 8px; }}
  h2 {{ color: #2563eb; font-size: 17px; margin-top: 28px; }}
  h3 {{ color: #374151; font-size: 14px; margin: 14px 0 4px 0; font-weight: 600; }}
  .section {{ background: #f0f7ff; border-left: 4px solid #2563eb; padding: 14px 18px;
              border-radius: 0 8px 8px 0; margin-bottom: 18px; }}
  .section-other {{ background: #faf5ff; border-left: 4px solid #7c3aed; padding: 14px 18px;
                    border-radius: 0 8px 8px 0; margin-bottom: 18px; }}
  ul {{ margin: 4px 0; padding-left: 18px; }}
  li {{ margin: 6px 0; line-height: 1.55; }}
  .footer {{ margin-top: 30px; padding-top: 14px; border-top: 1px solid #e5e7eb;
             font-size: 11px; color: #9ca3af; }}
</style>
</head>
<body>
  <h1>📋 Daily Action Items Digest</h1>
  <p style="color:#6b7280;margin-top:0;">{date_str} &nbsp;|&nbsp; Compiled from Fathom &amp; Notion meeting notes</p>

  <h2>🎯 Action Items Assigned to YOU ({len(my_items)} total)</h2>
  <div class="section">{items_html(my_items)}</div>

  <h2>👥 Action Items from Other People ({len(other_items)} total)</h2>
  <div class="section-other">{items_html(other_items)}</div>

  <div class="footer">
    This digest was auto-compiled from your Fathom recordings and Notion meeting notes
    (last {LOOKBACK_DAYS} day(s)).<br>
    Sent by Fidaris Daily Digest — runs every day at 6:00 PM
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def send_email(subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Digest sent to {RECIPIENT_EMAIL}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)
    today_label = now.strftime("%B %-d, %Y")
    print(f"Running daily digest for {today_label} (looking back {LOOKBACK_DAYS} day(s))")

    all_items: list[ActionItem] = []

    # --- Notion ---
    print("Fetching Notion meeting notes...")
    pages = get_recent_notion_meetings(since)
    print(f"  Found {len(pages)} recently edited meeting notes")
    for page in pages:
        title = extract_meeting_title(page)
        try:
            text = get_page_text(page["id"])
            items = extract_action_items_from_text(text, title)
            all_items.extend(items)
            if items:
                print(f"  • {title}: {len(items)} action item(s)")
        except Exception as e:
            print(f"  ⚠ Could not read page '{title}': {e}")

    # --- Fathom ---
    if FATHOM_API_TOKEN:
        print("Fetching Fathom meetings...")
        fathom_items = get_fathom_action_items(since)
        all_items.extend(fathom_items)
        print(f"  Found {len(fathom_items)} Fathom action item(s)")
    else:
        print("  ⚠ FATHOM_API_TOKEN not set — skipping Fathom")

    # --- Categorize ---
    my_items = [i for i in all_items if i.is_mine()]
    other_items = [i for i in all_items if not i.is_mine()]
    print(f"Total: {len(my_items)} mine, {len(other_items)} others")

    # --- Build & send ---
    html = build_email_html(my_items, other_items, now)
    subject = f"📋 Daily Action Items Digest — {today_label}"
    send_email(subject, html)


if __name__ == "__main__":
    main()
