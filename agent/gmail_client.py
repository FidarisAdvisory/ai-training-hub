import base64
import datetime
import email.utils
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from googleapiclient.discovery import build


def _build_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def get_unanswered_requests(credentials, user_email: str) -> list[dict]:
    """
    Find inbox threads from the last 7 days where the last message is not from user_email.
    These represent requests the user has received but not replied to.
    """
    service = _build_service(credentials)
    cutoff = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y/%m/%d")
    query = f"in:inbox -from:me after:{cutoff}"

    result = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    messages = result.get("messages", [])

    # Group by thread to find threads where the last message is not from the user
    thread_last: dict[str, dict] = {}
    for msg in messages:
        msg_data = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="metadata",
                 metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        thread_id = msg_data["threadId"]
        internal_date = int(msg_data.get("internalDate", 0))

        if thread_id not in thread_last or internal_date > thread_last[thread_id]["internal_date"]:
            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            thread_last[thread_id] = {
                "internal_date": internal_date,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": msg_data.get("snippet", ""),
                "msg_id": msg["id"],
            }

    unanswered = []
    today = datetime.date.today()
    for thread_id, data in thread_last.items():
        sender = data["from"].lower()
        # Skip if last message is from the user themselves
        if user_email.lower() in sender:
            continue
        msg_date = datetime.date.fromtimestamp(data["internal_date"] / 1000)
        age_days = (today - msg_date).days
        unanswered.append(
            {
                "subject": data["subject"],
                "sender": data["from"],
                "snippet": data["snippet"][:150],
                "date": msg_date.strftime("%b %-d"),
                "age_days": age_days,
            }
        )

    # Sort oldest first (most overdue at the top)
    unanswered.sort(key=lambda x: x["age_days"], reverse=True)
    return unanswered


def _build_html_wrapper(digest_html: str, today_date: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#1a1a2e;padding:20px 28px;">
      <p style="margin:0;color:#a0a8c0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Morning Briefing</p>
      <h1 style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:600;">{today_date}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {digest_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">Sent automatically by your Daily Priority Agent &mdash; Fidaris Advisory</p>
    </div>
  </div>
</body>
</html>"""


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_digest(credentials, recipient: str, digest_html: str, today_date: str) -> None:
    """Build and send the morning digest email via Gmail API."""
    service = _build_service(credentials)

    subject = f"Morning Priorities — {today_date}"
    full_html = _build_html_wrapper(digest_html, today_date)
    plain_text = _strip_html(full_html)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Daily Priority Agent <{os.environ.get('USER_EMAIL', recipient)}>"

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")


def send_action_items_digest(
    credentials, recipient: str, digest_html: str, today_date: str
) -> None:
    """Build and send the 6 PM action-items digest email via Gmail API."""
    service = _build_service(credentials)

    subject = f"📋 Daily Action Items Digest — {today_date}"

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:680px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#1e3a5f;padding:20px 28px;">
      <p style="margin:0;color:#a8c4e0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Daily Action Items Digest</p>
      <h1 style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:600;">{today_date}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:14px;line-height:1.6;">
      {digest_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">Sent automatically at 6 PM CT by your Daily Action Items Agent &mdash; Fidaris Advisory</p>
    </div>
  </div>
</body>
</html>"""

    plain_text = _strip_html(full_html)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Action Items Agent <{os.environ.get('USER_EMAIL', recipient)}>"

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Email sent to {recipient}: {subject}")
