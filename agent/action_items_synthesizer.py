"""
Claude-powered synthesis of daily action items from Fathom + Notion meeting notes.
Produces an HTML email body for the 6 PM evening digest.
"""
import datetime
import json
import os

import anthropic

SYSTEM_PROMPT = """You are a chief-of-staff assistant for Fidel Salazar at Fidaris Advisory.

Every evening you receive the day's meeting summaries (from Fathom emails and Notion notes) and produce a clean HTML action item digest to be sent at 6 PM.

RULES:
1. Extract ALL action items mentioned in the meeting content.
2. For each action item determine who it is assigned to.
3. Separate items into two groups:
   - "Mine" — items assigned to Fidel Salazar (also tagged as "Fidel", "me", "I will", "Fidel will", etc.)
   - "Others" — items assigned to other people. Include the assignee's name.
4. Group each section by project/meeting/client.
5. For each item include: the task description and the meeting it came from.
6. If a meeting has NO action items, skip it silently.
7. If there are no meetings at all, write a short message saying so.

OUTPUT: A valid HTML fragment (no <html>/<head>/<body> tags).
Use only inline styles. Follow this exact structure:

<h2 style="margin:0 0 4px;font-size:18px;color:#1a1a2e;">Action Item Digest &mdash; {date}</h2>
<p style="margin:0 0 20px;color:#718096;font-size:13px;">{N} meeting(s) reviewed &middot; {M} your items &middot; {K} others' items</p>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#1e3a5f;">✅ Your Action Items</h3>

<p style="margin:8px 0 4px;font-size:13px;font-weight:700;color:#2d6a9f;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e0eaf5;">{Project / Meeting Name}</p>
<ul style="margin:0 0 12px;padding-left:20px;">
  <li style="margin-bottom:6px;font-size:13.5px;">{task description}<br>
    <span style="font-size:11px;color:#9aa5b4;">From: {meeting name} &mdash; {date}</span></li>
</ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#5a4f8e;">👥 Others' Action Items</h3>

<p style="margin:8px 0 4px;font-size:13px;font-weight:700;color:#7c6bbf;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #ede9f6;">{Project / Meeting Name}</p>
<ul style="margin:0 0 12px;padding-left:20px;">
  <li style="margin-bottom:6px;font-size:13.5px;"><strong>{Assignee Name}</strong> &rarr; {task description}<br>
    <span style="font-size:11px;color:#9aa5b4;">From: {meeting name} &mdash; {date}</span></li>
</ul>

Keep descriptions concise (one sentence each). Max 900 words total."""


def synthesize_action_items(
    fathom_meetings: list[dict],
    notion_meetings: list[dict],
    today_date: str,
) -> str:
    """Call Claude to extract and format action items from today's meetings."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Build context from Fathom emails
    fathom_section = ""
    if fathom_meetings:
        items = []
        for m in fathom_meetings:
            items.append(f"MEETING: {m['subject']}\nDATE: {m['date']}\n\n{m['body']}")
        fathom_section = "=== FATHOM MEETING EMAILS ===\n\n" + "\n\n---\n\n".join(items)
    else:
        fathom_section = "=== FATHOM MEETING EMAILS ===\n(none found for today)"

    # Build context from Notion meeting notes
    notion_section = ""
    if notion_meetings:
        items = []
        for m in notion_meetings:
            items.append(
                f"MEETING: {m.get('title', 'Untitled')}\n"
                f"DATE: {m.get('date', '')}\n\n"
                f"{m.get('action_items', '(no action items extracted)')}"
            )
        notion_section = "=== NOTION MEETING NOTES ===\n\n" + "\n\n---\n\n".join(items)
    else:
        notion_section = "=== NOTION MEETING NOTES ===\n(none found for today)"

    user_message = f"""Today's date: {today_date}
User: Fidel Salazar (fidelsalazar@fidarisadvisory.com)

{fathom_section}

{notion_section}

Please extract all action items from these meetings and format the HTML digest."""

    response = client.messages.create(
        model=model,
        max_tokens=1800,
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
