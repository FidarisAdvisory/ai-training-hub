"""
Synthesizes Fathom action items into a formatted HTML email digest using Claude.
"""
import datetime
import json
import os

import anthropic

_SYSTEM_PROMPT = """You are a chief of staff for Fidel Salazar at Fidaris Advisory.
You receive a list of Fathom meeting recordings with their extracted action items.

YOUR JOB: produce a clean HTML email digest split into two sections:
  1. YOUR ITEMS — action items where the assignee is Fidel Salazar
  2. TEAM ITEMS — action items assigned to everyone else (people Fidel needs to follow up with)

CLASSIFICATION:
- Fidel's item = assignee field contains "Fidel" or "Fidel Salazar" (case-insensitive)
- Team item = any other assignee, including "Unassigned"
- Do NOT reclassify based on the task text — only the assignee field decides

ORGANIZATION (both sections):
- Group by meeting/project name, sorted by date (newest first)
- Show the meeting date next to the project title
- Mark TODAY's items with 🔴
- Include a clickable link on each item if clip_url is available (wrap the text in <a href=...>)
- Under Team Items, show the assignee name in muted italic before each task

OUTPUT: Valid HTML fragment only — no <html>/<head>/<body> tags, inline styles only.

Use this structure:

<h2 style="margin:0 0 4px;font-size:18px;color:#1a1a2e;">Action Items — {weekday, Month D}</h2>
<p style="margin:0 0 20px;color:#718096;font-size:14px;">{N} meetings · {N_yours} for you · {N_team} team items</p>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#2563eb;">🙋 Your Action Items</h3>
<p style="margin:12px 0 4px;font-size:14px;"><strong>{Meeting Title}</strong>&nbsp;<span style="color:#9ca3af;font-size:12px;">{date}</span></p>
<ul style="margin:0 0 8px;padding-left:20px;">
  <li style="margin-bottom:5px;">🔴 <a href="{clip_url}" style="color:#1a1a2e;text-decoration:none;">{text}</a></li>
  <li style="margin-bottom:5px;"><a href="{clip_url}" style="color:#1a1a2e;text-decoration:none;">{text}</a></li>
</ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#ea580c;">👥 Team Action Items</h3>
<p style="margin:12px 0 4px;font-size:14px;"><strong>{Meeting Title}</strong>&nbsp;<span style="color:#9ca3af;font-size:12px;">{date}</span></p>
<ul style="margin:0 0 8px;padding-left:20px;">
  <li style="margin-bottom:5px;"><span style="color:#6b7280;font-size:12px;font-style:italic;">{assignee}:</span>&nbsp;<a href="{clip_url}" style="color:#1a1a2e;text-decoration:none;">{text}</a></li>
</ul>

<p style="margin:20px 0 0;color:#9ca3af;font-size:12px;">Auto-generated from Fathom recordings · Fidaris Advisory</p>

If a section has no items, write: <p style="color:#9ca3af;font-size:13px;margin:4px 0 12px;">(none)</p>
Max 900 words. Do not truncate action items — show all of them."""


def synthesize_action_items(meetings: list[dict], today_date: str) -> str:
    """Call Claude to produce the HTML action items digest from meeting data."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    today_iso = datetime.date.today().isoformat()
    meetings_with_items = [m for m in meetings if m.get("action_items")]

    user_message = f"""Today: {today_date} ({today_iso})
User: Fidel Salazar

MEETINGS ({len(meetings_with_items)} with action items, sorted newest first):
{json.dumps(meetings_with_items, indent=2)}

Produce the HTML digest. Mark items from meetings dated {today_iso} with 🔴."""

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
