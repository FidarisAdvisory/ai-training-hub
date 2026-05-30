"""Entry point for the daily 6 PM action items digest."""

import base64
import datetime
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from googleapiclient.discovery import build

from agent.action_items_synthesizer import synthesize_action_items
from agent.auth import get_google_credentials
from agent.fathom_action_items import get_fathom_meetings


_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:680px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#1a1a2e;padding:20px 28px;">
      <p style="margin:0;color:#a0a8c0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Evening Briefing</p>
      <h1 style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:600;">{today_date}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {body}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">Sent automatically by your Daily Action Items Agent &mdash; Fidaris Advisory</p>
    </div>
  </div>
</body>
</html>"""


def _today_date(tz_name: str) -> str:
    tz = pytz.timezone(tz_name)
    return datetime.datetime.now(tz).strftime("%A, %B %d, %Y")


def _send(credentials, recipient: str, digest_html: str, today_date: str) -> None:
    import re

    def _strip(html: str) -> str:
        text = re.sub(r"<[^>]+>", "", html)
        for e, c in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&nbsp;", " "), ("&middot;", "·")]:
            text = text.replace(e, c)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    full_html = _WRAPPER.format(today_date=today_date, body=digest_html)
    plain = _strip(full_html)
    subject = f"📋 Daily Action Items Digest — {today_date}"
    sender = os.environ.get("USER_EMAIL", recipient)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Daily Action Items Agent <{sender}>"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    tz_name = os.environ.get("USER_TIMEZONE", "America/Chicago")
    today_date = _today_date(tz_name)

    print("Daily Action Items Agent starting...")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print("Fetching Fathom meeting emails (last 30 days)...")
    meetings = get_fathom_meetings(credentials, days_back=30)
    print(f"  Got {len(meetings)} meeting(s)")

    print("Parsing action items with Claude...")
    digest_html = synthesize_action_items(meetings, today_date)

    print(f"Sending email to {recipient}...")
    _send(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
