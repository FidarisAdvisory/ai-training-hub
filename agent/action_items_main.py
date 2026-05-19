"""
Daily Action Items Digest — runs at 6 PM CT.
Fetches Fathom recordings (last 30 days), splits action items into mine vs others,
synthesises HTML with Claude, and sends a real email via Gmail API.

Required environment variables:
  ANTHROPIC_API_KEY          Anthropic API key
  GOOGLE_CLIENT_ID           Google OAuth client ID
  GOOGLE_CLIENT_SECRET       Google OAuth client secret
  GOOGLE_REFRESH_TOKEN       Google OAuth refresh token
  FATHOM_API_KEY             Fathom API key (from fathom.video dashboard → Settings → API)
  RECIPIENT_EMAIL            Where to send the digest (e.g. fidelsalazar@fidarisadvisory.com)

Optional:
  USER_EMAIL                 Sender address (defaults to RECIPIENT_EMAIL)
  FATHOM_API_BASE            Fathom API base URL (default: https://api.fathom.video/v2)
  FATHOM_OWNER_NAME          Name to match for "my" items (default: Fidel Salazar)
  FATHOM_DAYS_BACK           Days of history to scan (default: 30)
  CLAUDE_MODEL               Claude model ID (default: claude-sonnet-4-6)
"""
import datetime
import os
import sys

from agent.action_items_synthesizer import synthesize_action_items_html
from agent.auth import get_google_credentials
from agent.fathom_client import get_recordings_with_action_items, split_action_items
from agent.gmail_client import send_action_items_digest


def main() -> None:
    recipient = os.environ["RECIPIENT_EMAIL"]
    days_back = int(os.environ.get("FATHOM_DAYS_BACK", "30"))
    owner_name = os.environ.get("FATHOM_OWNER_NAME", "Fidel Salazar")

    today_date = datetime.date.today().strftime("%A, %B %d, %Y")
    print(f"Daily Action Items Digest — {today_date}")

    print("Authenticating with Google...")
    credentials = get_google_credentials()

    print(f"Fetching Fathom recordings (last {days_back} days)...")
    recordings = get_recordings_with_action_items(days_back=days_back)
    total_ais = sum(len(r["action_items"]) for r in recordings)
    print(f"  {len(recordings)} recordings, {total_ais} action items total")

    print("Splitting action items...")
    mine, others = split_action_items(recordings, owner_name=owner_name)
    open_mine = [i for i in mine if not i.get("completed")]
    open_others = [i for i in others if not i.get("completed")]
    print(f"  Mine: {len(open_mine)} open | Others: {len(open_others)} open")

    if not open_mine and not open_others:
        print("No open action items found. Sending empty digest.")

    print("Synthesising HTML with Claude...")
    digest_html = synthesize_action_items_html(open_mine, open_others)

    print(f"Sending digest to {recipient}...")
    send_action_items_digest(credentials, recipient, digest_html, today_date)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
