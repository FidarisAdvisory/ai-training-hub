import datetime
import os
import sys

from agent.action_items_notion_client import get_open_action_items as get_notion_action_items
from agent.action_items_synthesizer import synthesize_action_items
from agent.auth import get_google_credentials
from agent.fathom_client import get_action_items as get_fathom_action_items
from agent.gmail_client import send_action_items_digest


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    user_email = os.environ.get("USER_EMAIL", recipient)

    print("Action Items Digest Agent starting...")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print("Fetching Fathom action items (last 30 days)...")
    fathom_data = get_fathom_action_items(user_email, days_back=30)
    print(f"  Mine: {len(fathom_data['mine'])}, Others: {len(fathom_data['others'])}")

    print("Fetching Notion action items (open/in-progress)...")
    notion_data = get_notion_action_items()
    print(f"  Mine: {len(notion_data['mine'])}, Others: {len(notion_data['others'])}")

    print("Synthesizing digest with Claude...")
    digest_html = synthesize_action_items(
        fathom_mine=fathom_data["mine"],
        fathom_others=fathom_data["others"],
        notion_mine=notion_data["mine"],
        notion_others=notion_data["others"],
    )

    today_date = datetime.date.today().strftime("%A, %B %d, %Y")
    print(f"Sending email to {recipient}...")
    send_action_items_digest(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
