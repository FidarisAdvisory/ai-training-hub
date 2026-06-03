"""
6 PM Action Item Digest
-----------------------
Reads today's Fathom meeting emails and Notion meeting notes,
extracts action items (yours vs. others), and sends an evening email.
"""
import base64
import datetime
import os
import re
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from googleapiclient.discovery import build

from agent.action_items_synthesizer import synthesize_action_items
from agent.auth import get_google_credentials
from agent.fathom_client import get_todays_fathom_meetings


# ---------------------------------------------------------------------------
# Notion meeting notes helper
# ---------------------------------------------------------------------------

def _get_notion_meetings_today(days_back: int = 1) -> list[dict]:
    """
    Query the Notion meetings database for notes created/edited today.
    Returns a list of dicts with title, date, and extracted action_items text.
    """
    token = os.environ.get("NOTION_API_TOKEN")
    meetings_db_id = os.environ.get("NOTION_MEETINGS_DATABASE_ID", "")

    if not token:
        print("  Notion not configured (NOTION_API_TOKEN missing). Skipping.")
        return []

    try:
        from notion_client import Client
        notion = Client(auth=token)
    except ImportError:
        print("  notion-client not installed. Skipping Notion meetings.")
        return []

    cutoff = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()
    results = []

    try:
        # Search for recently edited meeting pages
        search_resp = notion.search(
            filter={"property": "object", "value": "page"},
            sort={"direction": "descending", "timestamp": "last_edited_time"},
            page_size=20,
        )

        for page in search_resp.get("results", []):
            # Only include pages edited since our cutoff
            edited = page.get("last_edited_time", "")[:10]
            if edited < cutoff:
                continue

            props = page.get("properties", {})
            title = ""
            for prop in props.values():
                if prop.get("type") == "title":
                    title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                    break

            # Fetch the page blocks to find action items
            page_id = page["id"]
            try:
                blocks = notion.blocks.children.list(block_id=page_id, page_size=100)
                action_items = _extract_action_items_from_blocks(blocks.get("results", []))
                if action_items:
                    results.append({
                        "title": title or "Untitled",
                        "date": edited,
                        "action_items": action_items,
                    })
            except Exception as e:
                print(f"  Could not fetch blocks for page {page_id}: {e}")

    except Exception as e:
        print(f"  Notion meetings fetch error: {e}")

    print(f"  Notion: {len(results)} meeting page(s) with action items found")
    return results


def _extract_action_items_from_blocks(blocks: list) -> str:
    """
    Walk Notion blocks and extract text near action-item headings.
    Captures to_do blocks and text following 'Action Items' / 'Next Steps' headings.
    """
    lines = []
    in_action_section = False
    action_keywords = re.compile(r"action items?|next steps?|to[- ]dos?", re.IGNORECASE)

    for block in blocks:
        btype = block.get("type", "")
        rich = block.get(btype, {}).get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)

        if btype in ("heading_1", "heading_2", "heading_3"):
            in_action_section = bool(action_keywords.search(text))
            if in_action_section:
                lines.append(f"\n## {text}")
            continue

        if btype == "to_do":
            checked = block.get("to_do", {}).get("checked", False)
            prefix = "[x]" if checked else "[ ]"
            lines.append(f"{prefix} {text}")
        elif in_action_section and btype in ("bulleted_list_item", "numbered_list_item", "paragraph"):
            if text.strip():
                lines.append(f"- {text}")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Gmail sender
# ---------------------------------------------------------------------------

def _send_digest(credentials, recipient: str, digest_html: str, today_date: str) -> None:
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    subject = f"📋 Action Item Digest — {today_date}"

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:640px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2d6a9f 100%);padding:22px 28px;">
      <p style="margin:0;color:#a0b8d8;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Evening Briefing</p>
      <h1 style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:600;">Action Item Digest</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {digest_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">
        Sent automatically by your Action Item Digest Agent &mdash; Fidaris Advisory<br>
        Sources: Fathom meeting emails + Notion meeting notes
      </p>
    </div>
  </div>
</body>
</html>"""

    # Plain-text fallback
    plain = re.sub(r"<[^>]+>", "", full_html)
    plain = re.sub(r"&[a-z]+;", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Action Digest <{os.environ.get('USER_EMAIL', recipient)}>"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    tz_name = os.environ.get("USER_TIMEZONE", "America/Chicago")
    tz = pytz.timezone(tz_name)
    now = datetime.datetime.now(tz)
    today_date = now.strftime("%A, %B %-d, %Y")

    print("Action Item Digest Agent starting...")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print("Fetching today's Fathom meeting emails...")
    fathom_meetings = get_todays_fathom_meetings(credentials, days_back=1)

    print("Fetching today's Notion meeting notes...")
    notion_meetings = _get_notion_meetings_today(days_back=1)

    print("Synthesizing action items with Claude...")
    digest_html = synthesize_action_items(fathom_meetings, notion_meetings, today_date)

    print(f"Sending email to {recipient}...")
    _send_digest(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
