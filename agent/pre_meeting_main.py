import base64
import datetime
import os
import re
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from googleapiclient.discovery import build

from agent.auth import get_google_credentials
from agent.briefing_synthesizer import synthesize_pre_meeting_briefing
from agent.meeting_researcher import research_meeting


def _build_gmail_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def get_upcoming_meetings(credentials, tz: pytz.BaseTzInfo, window_min=25, window_max=45) -> list[dict]:
    """Return timed meetings starting between window_min and window_max minutes from now."""
    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    now = datetime.datetime.now(tz)
    start = now + datetime.timedelta(minutes=window_min)
    end = now + datetime.timedelta(minutes=window_max)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    meetings = []
    for item in result.get("items", []):
        start_data = item.get("start", {})
        end_data = item.get("end", {})
        # Skip all-day events
        if "date" in start_data and "dateTime" not in start_data:
            continue
        attendees = [
            {
                "email": a.get("email", ""),
                "name": a.get("displayName", a.get("email", "")),
            }
            for a in item.get("attendees", [])
            if not a.get("resource", False)
        ]
        meetings.append({
            "event_id": item.get("id", ""),
            "summary": item.get("summary", "(No title)"),
            "start": start_data.get("dateTime", ""),
            "end": end_data.get("dateTime", ""),
            "location": item.get("location", "") or item.get("hangoutLink", ""),
            "description": (item.get("description") or "")[:500],
            "attendees": attendees,
        })
    return meetings


def was_briefing_sent(credentials, event_id: str, today_str: str) -> bool:
    """Check Gmail sent folder to avoid sending duplicate briefings."""
    service = _build_gmail_service(credentials)
    marker = f"[PMB:{event_id[:16]}]"
    query = f'in:sent subject:"{marker}" after:{today_str}'
    try:
        result = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
        return len(result.get("messages", [])) > 0
    except Exception:
        return False


def send_briefing_email(credentials, recipient: str, briefing_html: str, meeting: dict) -> None:
    """Send the pre-meeting briefing via Gmail API."""
    service = _build_gmail_service(credentials)
    tz = pytz.timezone(os.environ.get("USER_TIMEZONE", "America/Chicago"))
    start_dt = datetime.datetime.fromisoformat(meeting["start"]).astimezone(tz)
    time_str = start_dt.strftime("%-I:%M %p")

    marker = f"[PMB:{meeting['event_id'][:16]}]"
    subject = f"Pre-Meeting Brief {marker}: {meeting['summary']} at {time_str}"

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#2d3748;padding:20px 28px;">
      <p style="margin:0;color:#a0aec0;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Pre-Meeting Brief &mdash; Starting in ~30 min</p>
      <h1 style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:600;">{meeting['summary']}</h1>
    </div>
    <div style="padding:24px 28px;color:#2d3748;font-size:15px;line-height:1.6;">
      {briefing_html}
    </div>
    <div style="padding:16px 28px;background:#f8f9fb;border-top:1px solid #e8ecf0;">
      <p style="margin:0;color:#9aa5b4;font-size:12px;">Sent by your Meeting Prep Agent &mdash; Fidaris Advisory</p>
    </div>
  </div>
</body>
</html>"""

    plain = re.sub(r"<[^>]+>", "", full_html)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = recipient
    msg["From"] = f"Meeting Prep Agent <{os.environ.get('USER_EMAIL', recipient)}>"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(full_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  Briefing sent: {subject}")


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    timezone_name = os.environ.get("USER_TIMEZONE", "America/Chicago")
    tz = pytz.timezone(timezone_name)
    today_str = datetime.date.today().strftime("%Y/%m/%d")

    print("Pre-Meeting Agent starting...")
    credentials = get_google_credentials()

    print("Checking for meetings starting in 25-45 minutes...")
    meetings = get_upcoming_meetings(credentials, tz)

    if not meetings:
        print("No upcoming meetings in window. Exiting.")
        return

    for meeting in meetings:
        print(f"Found: {meeting['summary']} at {meeting['start']}")

        # Skip solo blocks and internal placeholders — only brief meetings with real guests
        external_attendees = [
            a for a in meeting["attendees"]
            if a["email"].lower() != recipient.lower()
        ]
        if not external_attendees:
            print("  No external attendees — skipping.")
            continue

        if was_briefing_sent(credentials, meeting["event_id"], today_str):
            print("  Briefing already sent today. Skipping.")
            continue

        research = research_meeting(credentials, meeting)
        briefing_html = synthesize_pre_meeting_briefing(meeting, research)
        send_briefing_email(credentials, recipient, briefing_html, meeting)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
