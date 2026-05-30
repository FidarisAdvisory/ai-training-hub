"""Use Claude to parse Fathom emails and produce an action items HTML digest."""

import json
import os

import anthropic

SYSTEM_PROMPT = """You are an executive assistant for Fidel Salazar at Fidaris Advisory.

You receive raw Fathom meeting email bodies and must extract every action item, then split them into:
  - "mine"   : assigned to Fidel Salazar (or "Fidel")
  - "others" : assigned to anyone else

USER IDENTITY: Fidel Salazar  |  fidelsalazar@fidarisadvisory.com

OUTPUT: Return ONLY a valid JSON object in this exact shape — no markdown, no commentary:
{
  "mine": [
    {"action": "...", "project": "...", "date": "May 27"}
  ],
  "others": [
    {"action": "...", "project": "...", "assignee": "Person Name", "date": "May 27"}
  ]
}

Rules:
- Include ALL action items visible in the emails; do not skip any.
- Do not mark items as completed unless the body explicitly says [DONE] or similar.
- "project" should be a short, human-friendly label derived from the meeting title
  (e.g. "HighRadius | CFP - Go/No-Go" → "HighRadius Go-Live",
        "Daniel-Fidel connect - Revisión Fidaris O2C OS" → "Fidaris O2C SaaS MVP",
        "AI Training - Kevin Chandler - Session #3" → "AI Training – Kevin Chandler").
- "date" should be in "Mon DD" format (e.g. "May 27").
- For "assignee" in others[], use the person's name when available; otherwise their email local-part.
- Return ONLY the JSON object."""


def synthesize_action_items(meetings: list[dict], today_date: str) -> str:
    """
    Pass Fathom meeting bodies to Claude, get back structured action items,
    then render as an HTML fragment ready for embedding in the email wrapper.
    """
    if not meetings:
        return "<p style='color:#718096;'>No Fathom meetings found in the last 30 days.</p>"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    meetings_text = "\n\n=== MEETING ===\n".join(
        f"Subject: {m['title']}\nDate: {m['date']}\n\n{m['body']}"
        for m in meetings
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Today: {today_date}\n\n{meetings_text}",
        }],
    )

    raw = response.content[0].text.strip()
    # Strip optional markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  Claude JSON parse error: {e}. Raw snippet: {raw[:300]}")
        return "<p style='color:#c00;'>Error parsing action items — please check Fathom emails directly.</p>"

    return _render_html(data, today_date)


# ── HTML rendering ────────────────────────────────────────────────────────────

def _badge(text: str, color_bg: str, color_text: str) -> str:
    return (
        f"<span style='background:{color_bg};color:{color_text};"
        f"border-radius:10px;padding:2px 9px;font-size:12px;font-weight:600;'>{text}</span>"
    )


def _table_rows(items: list[dict], include_assignee: bool) -> str:
    rows = []
    for i, item in enumerate(items):
        bg = "#ffffff" if i % 2 == 0 else "#f9fafb"
        project_badge = _badge(item.get("project", ""), "#dbeafe", "#1d4ed8") if not include_assignee \
            else _badge(item.get("project", ""), "#ffedd5", "#c2410c")
        date_cell = f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;color:#6b7280;font-size:13px;'>{item.get('date','')}</td>"

        if include_assignee:
            assignee_cell = f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;font-weight:600;color:#374151;'>{item.get('assignee','')}</td>"
            rows.append(
                f"<tr style='background:{bg};'>"
                f"{assignee_cell}"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{item.get('action','')}</td>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{project_badge}</td>"
                f"{date_cell}"
                "</tr>"
            )
        else:
            rows.append(
                f"<tr style='background:{bg};'>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{item.get('action','')}</td>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{project_badge}</td>"
                f"{date_cell}"
                "</tr>"
            )
    return "\n".join(rows)


def _render_html(data: dict, today_date: str) -> str:
    mine = data.get("mine", [])
    others = data.get("others", [])

    header_style = "margin:20px 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;color:#718096;"
    th_style = "text-align:left;padding:8px 10px;color:#374151;"

    # ── Your action items ────────────────────────────────────────────────────
    mine_section = f"<h3 style='{header_style}'>✅ Your Action Items — Fidel Salazar</h3>"
    if mine:
        mine_section += (
            "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
            f"<tr style='background:#eef2ff;'>"
            f"<th style='{th_style}'>Action Item</th>"
            f"<th style='{th_style}width:200px;'>Project</th>"
            f"<th style='{th_style}width:70px;'>Date</th>"
            "</tr>"
            + _table_rows(mine, include_assignee=False)
            + "</table>"
        )
    else:
        mine_section += "<p style='color:#38a169;font-weight:600;'>🎉 No pending action items assigned to you.</p>"

    # ── Others' action items ─────────────────────────────────────────────────
    others_section = f"<h3 style='{header_style}margin-top:28px;'>👥 Action Items from Others</h3>"
    if others:
        others_section += (
            "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
            f"<tr style='background:#fff7ed;'>"
            f"<th style='{th_style}width:130px;'>Assigned To</th>"
            f"<th style='{th_style}'>Action Item</th>"
            f"<th style='{th_style}width:180px;'>Project</th>"
            f"<th style='{th_style}width:70px;'>Date</th>"
            "</tr>"
            + _table_rows(others, include_assignee=True)
            + "</table>"
        )
    else:
        others_section += "<p style='color:#718096;'>No pending action items assigned to others.</p>"

    return (
        f"<h2 style='margin:0 0 4px;font-size:18px;color:#1a1a2e;'>Action Items Digest</h2>"
        f"<p style='margin:0 0 20px;color:#718096;font-size:14px;'>"
        f"{today_date} &middot; Compiled from Fathom meetings (last 30 days)</p>"
        + mine_section
        + others_section
    )
