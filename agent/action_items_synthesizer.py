import datetime
import json
import os

import anthropic

_SYSTEM_PROMPT = """You are Fidel Salazar's chief of staff at Fidaris Advisory. Every evening at 6 PM you send him his daily action items digest.

You receive open action items from two sources:
  1. Fathom meeting recordings (last 30 days)
  2. Notion trackers (open/in-progress items)

RULES:
- Deduplicate: if the same action appears in both Fathom and Notion, show it once (Notion wins as authoritative).
- Mark Blocked items with ⚠️.
- Mark items whose deadline is today or past with a red badge: <span style="color:#e53e3e;font-size:11px;font-weight:600;">OVERDUE</span> or <span style="color:#d97706;font-size:11px;font-weight:600;">DUE TODAY</span>
- Sort within each group: overdue first, then by soonest deadline, then undated last.
- No preamble paragraphs — go straight into the sections.

SECTION 1 — MY ACTION ITEMS
Group by Client/Project (CEMEX, AI Trainings, CFP, DEACERO, Fidaris, Other).
For each item show:
  - Bold action text
  - Grey sub-line: source (meeting name or "Notion tracker") + deadline badge if applicable
  - Category/tower in brackets if available (e.g. [P2P], [M&A Playbook])

SECTION 2 — OTHERS' ACTION ITEMS
Group by person (assignee name + client in parentheses).
For each item show:
  - Bold action text
  - Grey sub-line: source (meeting name or tracker)
  - ⚠️ prefix if Blocked

OUTPUT: Valid HTML fragment, no <html>/<head>/<body> tags. Inline styles only.

Use this structure:
<h2 style="margin:0 0 4px;font-size:18px;color:#1a1a2e;">Action Items Digest — {date}</h2>
<p style="margin:0 0 20px;color:#718096;font-size:14px;">{N} open items for you · {M} pending from others</p>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Your Action Items</h3>
<p style="margin:12px 0 4px;font-weight:700;font-size:14px;color:#2d3748;">{Client}</p>
<ul style="margin:0 0 12px;padding-left:20px;">
  <li style="margin-bottom:8px;">
    <strong>{action text}</strong>
    <br><span style="color:#9aa5b4;font-size:12px;">{source} [{category}] {deadline_badge}</span>
  </li>
</ul>

<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;">Others' Action Items</h3>
<p style="margin:12px 0 4px;font-weight:700;font-size:14px;color:#2d3748;">{Person} ({Client})</p>
<ul style="margin:0 0 12px;padding-left:20px;">
  <li style="margin-bottom:8px;">
    <strong>{action text}</strong>
    <br><span style="color:#9aa5b4;font-size:12px;">{source}</span>
  </li>
</ul>"""


def synthesize_action_items(
    fathom_mine: list[dict],
    fathom_others: list[dict],
    notion_mine: list[dict],
    notion_others: list[dict],
) -> str:
    """Call Claude to produce the HTML digest from all action item sources."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    today = datetime.date.today().isoformat()

    user_message = f"""Today: {today}

MY ACTION ITEMS — FATHOM MEETINGS (last 30 days, open):
{json.dumps(fathom_mine, indent=2) if fathom_mine else "(none)"}

MY ACTION ITEMS — NOTION TRACKERS (not started / in progress):
{json.dumps(notion_mine, indent=2) if notion_mine else "(none)"}

OTHERS' ACTION ITEMS — FATHOM MEETINGS:
{json.dumps(fathom_others, indent=2) if fathom_others else "(none)"}

OTHERS' ACTION ITEMS — NOTION CEMEX TRACKER (not Fidel):
{json.dumps(notion_others, indent=2) if notion_others else "(none)"}

Deduplicate items that appear in both Fathom and Notion. Build the HTML digest now."""

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text
