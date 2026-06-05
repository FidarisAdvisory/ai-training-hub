"""
Evening Action Items Digest — main entry point.

Run:
  python -m agent.action_items_main

Required env vars:
  ANTHROPIC_API_KEY       — Anthropic API key
  GOOGLE_CLIENT_ID        — Google OAuth client ID
  GOOGLE_CLIENT_SECRET    — Google OAuth client secret
  GOOGLE_REFRESH_TOKEN    — Google OAuth refresh token (gmail.send scope)
  RECIPIENT_EMAIL         — where to send the digest
  FATHOM_API_KEY          — Fathom API token (Settings → API in Fathom web app)
  NOTION_API_TOKEN        — Notion integration secret
  NOTION_MEETINGS_DB      — Notion Meetings database ID
                            (c1e9cae0374049978086d3598f3d0f6a for Fidaris Advisory)

Optional:
  USER_EMAIL              — sender address (defaults to RECIPIENT_EMAIL)
  USER_TIMEZONE           — e.g. America/Chicago (default)
  CLAUDE_MODEL            — override the Claude model
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
from agent.fathom_client import get_fathom_action_items
from agent.notion_meeting_client import get_notion_meeting_action_items


def _build_html_email(digest_html: str, today_date: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:650px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#1a1a2e;padding:20px 28px;">
      <p style="margin:0;color:#a0a8c0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Evening Action Items Digest</p>
      <h1 style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:600;">{today_date}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {digest_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">
        Sent automatically at 6&nbsp;PM CT &mdash; Fidaris Advisory Action Items Agent<br>
        Sources: Fathom meeting recordings + Notion meeting notes (last 7 days)
      </p>
    </div>
  </div>
</body>
</html>"""


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    for ent, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&mdash;", "—")]:
        text = text.replace(ent, char)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def send_action_items_email(credentials, recipient: str, digest_html: str, today_date: str) -> None:
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    user_email = os.environ.get("USER_EMAIL", recipient)
    subject = f"Evening Action Items — {today_date}"

    full_html = _build_html_email(digest_html, today_date)
    plain_text = _strip_html(full_html)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Fidaris Action Items Agent <{user_email}>"
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    user_email = os.environ.get("USER_EMAIL", recipient)

    tz = pytz.timezone(os.environ.get("USER_TIMEZONE", "America/Chicago"))
    now = datetime.datetime.now(tz)
    today_date = now.strftime("%A, %B %-d, %Y")

    print("Evening Action Items Agent starting...")
    print(f"  Date: {today_date}")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print("Fetching Fathom action items (last 7 days)...")
    fathom_items = get_fathom_action_items(days_back=7)

    print("Fetching Notion meeting action items (last 7 days)...")
    notion_items = get_notion_meeting_action_items(days_back=7)

    all_items = fathom_items + notion_items
    print(f"  Total action items: {len(all_items)}")

    print("Synthesizing digest with Claude...")
    digest_html = synthesize_action_items(
        action_items=all_items,
        user_name="Fidel Salazar",
        today_date=today_date,
    )

    print(f"Sending email to {recipient}...")
    send_action_items_email(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
