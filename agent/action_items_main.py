"""
Evening Action Items Digest
Runs at 6 PM CT daily via GitHub Actions.

Required env vars:
  ANTHROPIC_API_KEY      - Claude API key
  FATHOM_API_KEY         - Fathom REST API key (from Fathom Settings > Integrations)
  GOOGLE_CLIENT_ID       - Google OAuth client ID
  GOOGLE_CLIENT_SECRET   - Google OAuth client secret
  GOOGLE_REFRESH_TOKEN   - Google OAuth refresh token
  RECIPIENT_EMAIL        - Email address to send the digest to
  USER_EMAIL             - Fidel's email (used as sender + assignee filter)

Optional env vars:
  NOTION_API_TOKEN       - Notion integration secret
  NOTION_MEETINGS_DB_ID  - Notion meetings database ID (supplements Fathom)
  USER_TIMEZONE          - Default: America/Chicago
  FATHOM_LOOKBACK_DAYS   - How many days back to pull meetings (default: 7)
"""

import datetime
import os
import sys

import pytz

from agent.action_items_synthesizer import synthesize_action_items_email
from agent.auth import get_google_credentials
from agent.fathom_client import get_action_items as fathom_get_action_items
from agent.gmail_client import send_digest
from agent.notion_meeting_client import get_meeting_action_items as notion_get_action_items


def _merge(a: dict, b: dict) -> dict:
    """Merge two {"mine": [...], "others": [...]} dicts, deduplicating by task text."""
    seen: set[str] = set()
    merged: dict[str, list] = {"mine": [], "others": []}
    for key in ("mine", "others"):
        for item in a.get(key, []) + b.get(key, []):
            sig = (item.get("task", "")[:80], item.get("meeting", ""))
            if sig not in seen:
                seen.add(sig)
                merged[key].append(item)
    return merged


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    user_email = os.environ.get("USER_EMAIL", recipient)
    user_name = os.environ.get("USER_NAME", "Fidel Salazar")
    tz = pytz.timezone(os.environ.get("USER_TIMEZONE", "America/Chicago"))
    lookback_days = int(os.environ.get("FATHOM_LOOKBACK_DAYS", "7"))

    now = datetime.datetime.now(tz)
    today_date = now.strftime("%A, %B %-d, %Y")

    print("Action Items Digest Agent starting...")

    print("Fetching Fathom action items...")
    fathom_data = fathom_get_action_items(
        days_back=lookback_days,
        user_email=user_email,
        user_name=user_name,
    )
    print(f"  Mine: {len(fathom_data['mine'])}, Others: {len(fathom_data['others'])}")

    print("Fetching Notion meeting action items...")
    notion_data = notion_get_action_items(days_back=lookback_days, user_name=user_name)
    print(f"  Mine: {len(notion_data['mine'])}, Others: {len(notion_data['others'])}")

    action_data = _merge(fathom_data, notion_data)
    print(
        f"Combined (deduplicated): {len(action_data['mine'])} mine, "
        f"{len(action_data['others'])} others"
    )

    print("Synthesizing digest with Claude...")
    digest_html = synthesize_action_items_email(action_data, today_date, user_name)

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print(f"Sending digest to {recipient}...")
    send_digest(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
