import datetime
import json
import os

import anthropic

SYSTEM_PROMPT = """You are a personal chief of staff for a busy advisor at Fidaris Advisory. Every morning you receive their calendar events, Notion tasks, unanswered emails, and financial data, then produce a structured morning briefing.

INSTRUCTIONS:

1. CALENDAR PRIORITIES (today only)
   - List today's events/tasks in order of: (a) fixed meeting times, (b) hard deadlines, (c) strategic importance.
   - For each item, add one sentence of context on what to focus on or watch out for.

2. EMAILS REQUIRING ACTION
   - Show ALL unanswered email threads. Do not filter any out.
   - Group them: (a) Urgent - needs reply today, (b) This week - can wait.
   - One sentence per email on what action is needed.
   - Flag emails waiting more than 2 days in red.
   - If empty: "Inbox clear - no pending replies."

3. TOMORROW OVERVIEW
   - All meetings with times, open blocks of 30+ min, day rating (Light/Moderate/Heavy).
   - Flag any tomorrow meetings needing prep today.

4. MEETING PREP ALERTS (today)
   - Flag today's meetings needing prep without a prep block. Suggest a time window.
   - Confirm meetings with an existing prep block.

5. REVENUE & PIPELINE
   - ALWAYS include this section, no matter what the values are.
   - If revenue data is "(not available)": write "⚠️ Revenue data not configured — verify NOTION_API_TOKEN is set in GitHub secrets and that the Notion integration is connected to the CEMEX, CFP, and DEACERO time log databases."
   - If revenue data is present (even if $0): show the per-client breakdown (hours × rate = amount), total MTD, and pace vs month progress.
   - If a client shows 0 hours, just display it as 0 hrs × rate = $0.
   - If access_errors are listed in the data, show them as a warning: "⚠️ Could not access: {error list} — open Notion, go to each database, click ··· → Connections → add your integration."
   - Show total active AI training pipeline value and number of active leads.
   - List HIGH priority leads only, with: name, company, stage, value, next action, and due date.
   - If pipeline shows 0 leads, write "(no active high-priority leads)".

6. SUGGESTED FOCUS BLOCK
   - Best open window today for deep work, with a specific suggestion.

OUTPUT FORMAT: Valid HTML fragment, no <html>/<head>/<body> tags, inline styles only.

<h2 style="margin:0 0 4px;font-size:18px;color:#1a1a2e;">Today - {weekday, date}</h2>
<p style="margin:0 0 20px;color:#718096;font-size:14px;">{theme of the day}</p>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Calendar Priorities</h3>
<ol style="margin:0;padding-left:20px;"><li style="margin-bottom:10px;"><strong>{time} - {title}</strong>: {context}</li></ol>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Emails Requiring Action</h3>
<ul style="margin:0;padding-left:20px;"><li style="margin-bottom:8px;"><strong>{Sender}</strong>: {Subject} <span style="color:#718096;font-size:13px;">({age})</span><br><span style="font-size:13px;color:#4a5568;">{action needed}</span></li></ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Tomorrow Overview - {date}</h3>
<p style="margin:0 0 6px;"><strong>Load:</strong> {Light/Moderate/Heavy} &mdash; {N} meetings</p>
<ul style="margin:0 0 10px;padding-left:20px;"><li>{time} - {meeting}</li></ul>
<p style="margin:0 0 6px;"><strong>Open blocks:</strong> {gaps or "None"}</p>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Meeting Prep Alerts</h3>
<ul style="margin:0;padding-left:20px;"><li><span style="color:#d97706;font-weight:600;">&#9888; {meeting}</span> - No prep block. Use {window}.<br><!-- or: <span style="color:#38a169;font-weight:600;">&#10003; {meeting}</span> - Prep at {time}. --></li></ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Revenue &amp; Pipeline</h3>
<p style="margin:0 0 6px;"><strong>{Month} MTD:</strong> <span style="font-size:16px;font-weight:700;color:#2d3748;">${total_earned}</span> &mdash; Day {N} of {total} ({pct}% of month)</p>
<ul style="margin:0 0 12px;padding-left:20px;">
  <li>CEMEX: {hrs} hrs &times; $125 = <strong>${amount}</strong></li>
  <li>CFP: {hrs} hrs &times; $125 = <strong>${amount}</strong></li>
  <li>DEACERO: {hrs} hrs &times; $82 = <strong>${amount}</strong></li>
</ul>
<p style="margin:0 0 6px;"><strong>AI Training Pipeline:</strong> ${pipeline_total} &mdash; {N} active leads</p>
<ul style="margin:0;padding-left:20px;"><li style="margin-bottom:6px;"><strong>{name}</strong> ({company}) &mdash; {stage} &mdash; <span style="color:#38a169;font-weight:600;">${value}</span> &mdash; {next_action} by {date}</li></ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Suggested Focus Block</h3>
<p style="margin:0;">{window} - {what to work on}</p>

Max 700 words total."""


def synthesize_priorities(
    calendar_data: dict,
    notion_data: dict,
    unanswered_emails: list[dict],
    revenue_data: dict,
) -> str:
    """Call Claude to produce the HTML digest from all data sources."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    today = datetime.date.today()
    if today.month == 12:
        days_in_month = 31
    else:
        days_in_month = (today.replace(month=today.month + 1, day=1) - datetime.timedelta(days=1)).day
    month_progress_pct = round(today.day / days_in_month * 100)

    user_message = f"""Date: {calendar_data['today_date']}
Current time: {calendar_data['current_time']}
Timezone: {os.environ.get('USER_TIMEZONE', 'America/Chicago')}
Month progress: Day {today.day} of {days_in_month} ({month_progress_pct}% elapsed)

CALENDAR - TODAY ({calendar_data['today_date']}):
{json.dumps(calendar_data['today'], indent=2) if calendar_data['today'] else '(no events)'}

CALENDAR - TOMORROW ({calendar_data['tomorrow_date']}):
{json.dumps(calendar_data['tomorrow'], indent=2) if calendar_data['tomorrow'] else '(no events)'}

NOTION TASKS - TODAY:
{json.dumps(notion_data['today'], indent=2) if notion_data['today'] else '(none)'}

NOTION TASKS - TOMORROW:
{json.dumps(notion_data['tomorrow'], indent=2) if notion_data['tomorrow'] else '(none)'}

UNANSWERED EMAILS (last 7 days, oldest first):
{json.dumps(unanswered_emails, indent=2) if unanswered_emails else '(none - inbox clear)'}

REVENUE & PIPELINE:
{json.dumps(revenue_data, indent=2) if revenue_data else '(not available)'}

Reminders:
- Show ALL unanswered emails, no filtering.
- List every tomorrow meeting with times and calculate open gaps.
- In Revenue, show per-client breakdown and pace vs month progress.
- For pipeline, show high-priority leads with next action dates."""

    response = client.messages.create(
        model=model,
        max_tokens=1600,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text
