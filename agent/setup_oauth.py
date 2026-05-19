"""
One-time OAuth2 setup script — run this locally to obtain a refresh token.

Usage:
  1. Create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console.
     Enable: Google Calendar API, Gmail API, and Google Drive API.
  2. Set environment variables:
       export GOOGLE_CLIENT_ID=<your-client-id>
       export GOOGLE_CLIENT_SECRET=<your-client-secret>
  3. Run: python -m agent.setup_oauth
  4. Authorize in the browser that opens.
  5. Copy the printed GOOGLE_REFRESH_TOKEN into your GitHub Actions secrets.

This script is never executed by GitHub Actions.
"""

import os

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def run_oauth_flow() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or input("Enter GOOGLE_CLIENT_ID: ").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or input("Enter GOOGLE_CLIENT_SECRET: ").strip()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Run: pip install google-auth-oauthlib")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("SUCCESS! Add the following to your GitHub Actions secrets:")
    print("=" * 60)
    print(f"\nGOOGLE_CLIENT_ID     = {client_id}")
    print(f"GOOGLE_CLIENT_SECRET = {client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN = {credentials.refresh_token}")
    print("\nAlso add these repository variables (not secrets):")
    print("USER_EMAIL           = fidelsalazar@fidarisadvisory.com")
    print("=" * 60)


if __name__ == "__main__":
    run_oauth_flow()
