# Daily Action Items Digest — Setup Guide

The `daily-action-items.yml` workflow runs every day at 6:00 PM CDT and sends
Fidel a compiled list of open action items from all Fathom meetings and Notion
meeting notes.

## Required GitHub Repository Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and
add each of the following:

### 1. `ANTHROPIC_API_KEY`
Your Anthropic API key from https://console.anthropic.com/settings/keys

### 2. `FATHOM_API_KEY`
Your Fathom API key. Get it from:
https://fathom.video/settings/developer

### 3. `NOTION_API_KEY`
A Notion internal integration token with access to your Meetings database.
Create one at: https://www.notion.so/my-integrations
- Make sure to share your Meetings database with the integration.

### 4. Gmail OAuth2 — Three secrets needed

Gmail requires OAuth2. The easiest way is to use the **Google OAuth2 Playground**:

1. Go to https://developers.google.com/oauthplayground
2. In Settings (gear icon), check "Use your own OAuth credentials"
3. Enter your Google Cloud OAuth client credentials
4. Authorize the `https://mail.google.com/` scope
5. Exchange auth code for tokens — copy the **refresh token**

Then set these secrets:
- `GMAIL_OAUTH_CLIENT_ID` — from Google Cloud Console
- `GMAIL_OAUTH_CLIENT_SECRET` — from Google Cloud Console
- `GMAIL_OAUTH_REFRESH_TOKEN` — from the playground step above

## Adjusting the Timezone

The cron schedule `0 23 * * *` triggers at 6 PM CDT (UTC-5).
In winter (Nov–Mar, CST = UTC-6), change to `0 0 * * *` to keep 6 PM local time.

## Manual Test Run

To run immediately without waiting for 6 PM:
1. Go to **Actions → Daily Action Items Digest**
2. Click **Run workflow → Run workflow**

## What the Digest Includes

- **Your Action Items** (Fidel Salazar) — organized by project:
  - CEMEX Alpha (P2P, R2R, O2C)
  - HighRadius / CFP
  - LSU Healthcare
  - AI Training clients
  - Fidaris Business Development
- **Other People's Action Items** — with assignee name and project
- Source: Fathom meeting recordings (last 30 days) + Notion meeting notes
