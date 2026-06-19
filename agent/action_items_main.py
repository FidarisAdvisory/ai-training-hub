"""
Daily Action Items Digest agent.

Fetches Fathom meeting action items from the past N days, synthesizes them with
Claude into a two-section digest (your items / team items), and sends the email
via Gmail.

Required env vars:
  ANTHROPIC_API_KEY
  FATHOM_API_KEY        — from fathom.video/app/settings/api-tokens
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REFRESH_TOKEN
  RECIPIENT_EMAIL

Optional:
  USER_EMAIL            — shown as From address (defaults to RECIPIENT_EMAIL)
  FATHOM_DAYS_BACK      — how many days of meetings to include (default: 7)
"""
import base64
import datetime
import os
import re
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from agent.action_items_synthesizer import synthesize_action_items
from agent.auth import get_google_credentials
from agent.fathom_client import get_meetings_with_action_items

_HEADER_STYLE = "background:#1a1a2e;padding:20px 28px;"
_WRAPPER_STYLE = (
    "max-width:640px;margin:24px auto;background:#ffffff;"
    "border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);"
)


def _wrap_html(digest_html: str, today_date: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="{_WRAPPER_STYLE}">
    <div style="{_HEADER_STYLE}">
      <p style="margin:0;color:#a0a8c0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Daily Digest</p>
      <h1 style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:600;">Action Items — {today_date}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {digest_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">Daily Action Items Digest &mdash; Fidaris Advisory</p>
    </div>
  </div>
</body>
</html>"""


def _send_email(credentials, recipient: str, full_html: str, today_date: str) -> None:
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    subject = f"📋 Action Items Digest — {today_date}"
    plain = re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "", full_html)).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Action Items Agent <{os.environ.get('USER_EMAIL', recipient)}>"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    fathom_api_key = os.environ["FATHOM_API_KEY"]
    days_back = int(os.environ.get("FATHOM_DAYS_BACK", "7"))
    today_date = datetime.date.today().strftime("%A, %B %d, %Y")

    print("Action Items Digest starting...")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print(f"Fetching Fathom meetings (past {days_back} days)...")
    meetings = get_meetings_with_action_items(fathom_api_key, days_back=days_back)
    n_items = sum(len(m["action_items"]) for m in meetings)
    print(f"  {len(meetings)} meetings with action items · {n_items} total items")

    if not meetings:
        print("No action items found — skipping email.")
        return

    print("Synthesizing digest with Claude...")
    digest_html = synthesize_action_items(meetings, today_date)

    print(f"Sending email to {recipient}...")
    full_html = _wrap_html(digest_html, today_date)
    _send_email(credentials, recipient, full_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
