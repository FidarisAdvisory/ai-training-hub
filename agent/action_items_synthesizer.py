import datetime
import json
import os

import anthropic

SYSTEM_PROMPT = """You are a chief-of-staff assistant for Fidel Salazar at Fidaris Advisory.
Your job: format a daily action-items digest as an HTML fragment (no <html>/<head>/<body> tags, inline styles only).

INPUT: Two JSON arrays — "mine" (action items assigned to Fidel) and "others" (items assigned to other people).
Each item has: text, assignee, meeting_title, meeting_date, meeting_url.

OUTPUT RULES:
- Group items by project/meeting context (infer the project from meeting_title).
- Within each project group, list items as <li> elements.
- For "others", prefix each item with the assignee name in bold.
- Keep meeting dates for reference. Link meeting_title to meeting_url if url is present.
- Use the colour palette: mine = #1e3a5f (dark blue), others = #8b3a1e (dark orange).
- Do not include completed items.
- If a project group has > 8 items, still show all of them.
- Output only the inner HTML fragment — no wrapper divs, no preamble text.

STRUCTURE:
<h2 style="...">✅ My Action Items (N)</h2>
<h3 style="... project-heading">Project Name</h3>
<ul>...</ul>
... (repeat per project)

<h2 style="...">👥 Others' Action Items (N)</h2>
<h3 style="... project-heading">Project Name</h3>
<ul>...</ul>
... (repeat per project)"""


def synthesize_action_items_html(mine: list[dict], others: list[dict]) -> str:
    """Call Claude to produce the HTML digest for the action items."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    today = datetime.date.today().strftime("%A, %B %d, %Y")

    user_message = f"""Date: {today}

MY ACTION ITEMS ({len(mine)} open):
{json.dumps(mine, indent=2) if mine else '[]'}

OTHERS' ACTION ITEMS ({len(others)} open):
{json.dumps(others, indent=2) if others else '[]'}

Produce the HTML digest fragment now. Group items by project, link meeting titles to URLs where available."""

    response = client.messages.create(
        model=model,
        max_tokens=3000,
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
