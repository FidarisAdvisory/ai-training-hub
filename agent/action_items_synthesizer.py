import datetime
import os
from collections import defaultdict

import anthropic

SYSTEM_PROMPT = """You are a chief-of-staff assistant for Fidel Salazar at Fidaris Advisory.
Every evening at 6 PM you receive a structured list of action items extracted from his Fathom meeting recordings and Notion meeting notes.

Your job is to produce a clean, scannable HTML email digest that shows:
1. Fidel's own action items — grouped by project/client, sorted most-recent-meeting first.
2. Other people's pending action items (commitments they owe Fidel or the project) — grouped by project/client.

INSTRUCTIONS:
- Group action items under a bold project/client heading derived from the meeting title.
- Inside each group, list items as checkboxes (☐) with a short task description and the meeting date in gray.
- For "others" items, prepend the assignee name in a pill badge.
- Flag items older than 3 days with ⚠️ to indicate they may need a follow-up.
- Do NOT include duplicate items. If a task appears identically in multiple sources, show it once.
- Keep the output tight — no unnecessary prose, just the structured digest.
- End with a one-sentence "Focus Recommendation" suggesting the single most impactful thing Fidel should tackle first tomorrow morning.

OUTPUT FORMAT: Valid HTML fragment (no <html>/<head>/<body> tags). Use only inline styles.
Max 900 words."""

_PILL = (
    'style="display:inline-block;padding:1px 8px;border-radius:10px;'
    'font-size:11px;font-weight:600;color:#fff;background:{bg};margin-right:6px;"'
)
_PILL_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444", "#6366f1"]


def synthesize_action_items_email(
    action_data: dict,
    today_date: str,
    user_name: str = "Fidel Salazar",
) -> str:
    """
    Call Claude to render the HTML digest. Falls back to a local renderer
    if ANTHROPIC_API_KEY is not set (useful for testing).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _local_render(action_data, today_date, user_name)

    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    mine = action_data.get("mine", [])
    others = action_data.get("others", [])

    today = datetime.date.today()

    def age_flag(date_str: str) -> str:
        try:
            d = datetime.date.fromisoformat(date_str)
            if (today - d).days > 3:
                return " ⚠️"
        except ValueError:
            pass
        return ""

    def fmt_item(item: dict, include_assignee: bool = False) -> str:
        flag = age_flag(item["date"])
        assignee_part = f"[{item['assignee']}] " if include_assignee and item.get("assignee") else ""
        return (
            f"  ☐ {assignee_part}{item['task']}{flag}  "
            f"({item['meeting']} · {item['date']})"
        )

    mine_text = _group_by_meeting(mine, fmt_item, include_assignee=False)
    others_text = _group_by_meeting(others, fmt_item, include_assignee=True)

    user_message = f"""Date: {today_date}
User: {user_name}

=== {user_name.upper()}'S ACTION ITEMS ({len(mine)} items) ===
{mine_text if mine_text else "(none)"}

=== OTHERS' PENDING COMMITMENTS ({len(others)} items) ===
{others_text if others_text else "(none)"}

Produce the evening action items digest email HTML fragment now."""

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


def _group_by_meeting(items: list[dict], fmt_fn, include_assignee: bool) -> str:
    grouped: dict[str, list] = defaultdict(list)
    for item in items:
        grouped[item["meeting"]].append(item)

    lines = []
    for meeting, meeting_items in grouped.items():
        lines.append(f"\n[{meeting}]")
        for item in meeting_items:
            lines.append(fmt_fn(item, include_assignee))
    return "\n".join(lines)


def _local_render(action_data: dict, today_date: str, user_name: str) -> str:
    """Minimal HTML renderer used when no Anthropic API key is available."""
    mine = action_data.get("mine", [])
    others = action_data.get("others", [])
    today = datetime.date.today()

    def age_flag(date_str: str) -> str:
        try:
            if (today - datetime.date.fromisoformat(date_str)).days > 3:
                return " ⚠️"
        except ValueError:
            pass
        return ""

    def render_group(items: list[dict], show_assignee: bool) -> str:
        if not items:
            return "<p style='color:#888;font-size:13px;'>(none)</p>"
        grouped: dict[str, list] = defaultdict(list)
        for item in items:
            grouped[item["meeting"]].append(item)
        html = ""
        for meeting, mitems in grouped.items():
            html += f"<p style='font-size:12px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.5px;margin:16px 0 6px;border-bottom:1px solid #eee;padding-bottom:3px;'>{meeting}</p><ul style='margin:0;padding-left:0;list-style:none;'>"
            for item in mitems:
                flag = age_flag(item["date"])
                assignee_html = ""
                if show_assignee and item.get("assignee"):
                    idx = hash(item["assignee"]) % len(_PILL_COLORS)
                    bg = _PILL_COLORS[idx]
                    assignee_html = f"<span {_PILL.format(bg=bg)}>{item['assignee']}</span>"
                html += (
                    f"<li style='display:flex;align-items:flex-start;gap:6px;padding:5px 0;border-bottom:1px dotted #f0f0f0;font-size:14px;'>"
                    f"<span style='color:#ccc;'>☐</span>"
                    f"<span style='flex:1;line-height:1.4;'>{assignee_html}{item['task']}{flag}"
                    f" <span style='color:#aaa;font-size:11px;'>· {item['date']}</span></span></li>"
                )
            html += "</ul>"
        return html

    return f"""
<h2 style="margin:0 0 4px;font-size:18px;color:#1a2e4a;">Evening Action Items Digest</h2>
<p style="margin:0 0 20px;color:#718096;font-size:14px;">{today_date} &mdash; {len(mine)} yours &middot; {len(others)} others</p>
<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:#1a56db;">🔵 {user_name}'s Action Items</h3>
{render_group(mine, False)}
<h3 style="margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:#b45309;">🟡 Others' Pending Commitments</h3>
{render_group(others, True)}
"""
