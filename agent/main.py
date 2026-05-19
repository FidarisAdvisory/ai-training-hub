import os
import sys

from agent.auth import get_google_credentials
from agent.calendar_client import get_calendar_data
from agent.claude_synthesizer import synthesize_priorities
from agent.gmail_client import get_unanswered_requests, send_digest
from agent.notion_client import get_notion_tasks
from agent.revenue_client import get_monthly_revenue


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    user_email = os.environ.get("USER_EMAIL", recipient)

    print("Daily Priority Agent starting...")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print("Fetching calendar events...")
    calendar_data = get_calendar_data(credentials)
    print(f"  Today: {len(calendar_data['today'])} events")
    print(f"  Tomorrow: {len(calendar_data['tomorrow'])} events")

    print("Fetching Notion tasks...")
    notion_data = get_notion_tasks(calendar_data["today_date"], calendar_data["tomorrow_date"])
    print(f"  Today: {len(notion_data['today'])} tasks, Tomorrow: {len(notion_data['tomorrow'])} tasks")

    print("Fetching revenue & pipeline data...")
    revenue_data = get_monthly_revenue(credentials)

    print("Scanning for unanswered emails...")
    unanswered = get_unanswered_requests(credentials, user_email)
    print(f"  Found {len(unanswered)} unanswered thread(s)")

    print("Synthesizing priorities with Claude...")
    digest_html = synthesize_priorities(calendar_data, notion_data, unanswered, revenue_data)

    print(f"Sending email to {recipient}...")
    send_digest(credentials, recipient, digest_html, calendar_data["today_date"])

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
