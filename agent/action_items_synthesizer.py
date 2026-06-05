"""
Claude-powered synthesizer for the 6 PM action items digest email.

Takes raw action items from Fathom + Notion and produces a structured HTML email
with two sections: items assigned to the user, and items assigned to others.
"""

import json
import os

import anthropic


SYSTEM_PROMPT = """You are a chief-of-staff assistant for Fidel Salazar at Fidaris Advisory.
Your job is to produce a clean evening action items digest email in HTML format.

You receive a list of raw action items from Fathom meeting recordings and Notion meeting notes.
Each item has: meeting_title, meeting_date, task, assignee, and optionally assignee_email.

INSTRUCTIONS:
1. Split items into two groups:
   - "Mine" — assigned to Fidel Salazar (or "Fidel")
   - "Others" — assigned to anyone else
2. Within each group, cluster items by PROJECT (infer the project from meeting title).
   Use short, clear project names like: "HighRadius | CFP", "Kevin Chandler Coaching",
   "CEMEX P2P", "Valcourt AI Training", "Fidaris O2C SaaS", etc.
3. List the most recent items first within each project.
4. For each item include: the task, the meeting name, and the date.
5. Skip any items that appear trivially completed or are clearly duplicates.
6. If there are no items in a section, write "(None today)".

OUTPUT: A valid HTML fragment (no <html>/<head>/<body> tags). Use inline styles.
Keep the layout clean and scannable. Use these exact section headers:

<h2>Action Items Assigned to You — Fidel Salazar</h2>
... grouped by project ...

<h2>Action Items from Other People</h2>
... grouped by project + person ...

Color scheme: your items use #4a86e8 (blue), others use #e8874a (orange).
Project headers: bold, 14px, with a left border.
Task items: bullet list, 13px.
Source line: italic, gray, 11px.
Max 900 words total."""


def synthesize_action_items(
    action_items: list[dict],
    user_name: str = "Fidel Salazar",
    today_date: str = "",
) -> str:
    """Call Claude to produce the HTML digest from all action items."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    if not action_items:
        return "<p>No open action items found in recent meetings.</p>"

    user_message = f"""Date: {today_date}
User: {user_name} (fidelsalazar@fidarisadvisory.com)

RAW ACTION ITEMS ({len(action_items)} total from Fathom + Notion, last 7 days):
{json.dumps(action_items, indent=2)}

Please produce the evening action items digest HTML."""

    response = client.messages.create(
        model=model,
        max_tokens=2000,
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
