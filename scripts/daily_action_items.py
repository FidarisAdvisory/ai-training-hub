#!/usr/bin/env python3
"""
Daily Action Items Digest
Pulls action items from Fathom meetings and Notion meeting notes,
then emails a formatted digest to Fidel Salazar at 6 PM.

Required environment variables:
  FATHOM_API_KEY       - Fathom REST API key (Settings → Integrations → API)
  NOTION_API_KEY       - Notion integration secret (notion.so/my-integrations)
  NOTION_MEETINGS_DB   - Notion meetings database ID (from the Meetings DB URL)
  GMAIL_SENDER         - Gmail address to send from
  GMAIL_APP_PASSWORD   - Gmail App Password (not your account password)
  DIGEST_RECIPIENT     - Email address to receive the digest
"""

import os
import json
import smtplib
import datetime
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── Config ────────────────────────────────────────────────────────────────────

FATHOM_API_KEY     = os.environ["FATHOM_API_KEY"]
NOTION_API_KEY     = os.environ["NOTION_API_KEY"]
NOTION_MEETINGS_DB = os.environ["NOTION_MEETINGS_DB"]
GMAIL_SENDER       = os.environ["GMAIL_SENDER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
DIGEST_RECIPIENT   = os.environ.get("DIGEST_RECIPIENT", GMAIL_SENDER)

# How many days back to look for meetings
LOOKBACK_DAYS = 14

ME_NAME  = "Fidel Salazar"
ME_EMAIL = "fidelsalazar@fidarisadvisory.com"


# ── Fathom ────────────────────────────────────────────────────────────────────

def fetch_fathom_action_items(since: datetime.datetime) -> list[dict]:
    """Return action items from all meetings recorded since `since`."""
    headers = {"Authorization": f"Bearer {FATHOM_API_KEY}"}
    base    = "https://api.fathom.video/v1"
    items   = []
    cursor  = None

    while True:
        params = {"include_action_items": "true", "page_size": 20}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(f"{base}/calls", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for call in data.get("calls", []):
            started = call.get("started_at", "")
            if started:
                call_dt = datetime.datetime.fromisoformat(started.replace("Z", "+00:00"))
                if call_dt.replace(tzinfo=None) < since.replace(tzinfo=None):
                    return items  # results are newest-first; stop when too old

            title      = call.get("title", "Untitled Meeting")
            call_url   = call.get("url", "")
            date_str   = started[:10] if started else ""

            for ai in call.get("action_items", []):
                items.append({
                    "task":     ai.get("text", "").strip(),
                    "assignee": ai.get("assignee_name", "").strip(),
                    "meeting":  title,
                    "date":     date_str,
                    "url":      ai.get("url") or call_url,
                })

        cursor = data.get("next_cursor")
        if not cursor:
            break

    return items


# ── Notion ────────────────────────────────────────────────────────────────────

def fetch_notion_action_items(since: datetime.datetime) -> list[dict]:
    """Return action items parsed from Notion meeting note blocks."""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    items    = []
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Query the Meetings database for recently edited pages
    payload = {
        "filter": {
            "property": "last_edited_time",
            "date": {"on_or_after": since_iso},
        },
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        "page_size": 50,
    }
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_MEETINGS_DB}/query",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("results", [])

    for page in pages:
        page_id   = page["id"]
        title_prop = page.get("properties", {}).get("title") or page.get("properties", {}).get("Name")
        title     = ""
        if title_prop and title_prop.get("title"):
            title = "".join(t.get("plain_text", "") for t in title_prop["title"])
        if not title:
            title = "Notion Meeting Note"

        date_str = page.get("last_edited_time", "")[:10]

        # Walk the page blocks looking for to-do checkboxes
        page_items = _extract_todos_from_page(page_id, headers, title, date_str)
        items.extend(page_items)

    return items


def _extract_todos_from_page(
    page_id: str,
    headers: dict,
    title: str,
    date_str: str,
    max_blocks: int = 200,
) -> list[dict]:
    items  = []
    cursor = None
    seen   = 0

    while seen < max_blocks:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            break
        data   = resp.json()
        blocks = data.get("results", [])
        seen  += len(blocks)

        for block in blocks:
            if block.get("type") == "to_do":
                td      = block["to_do"]
                checked = td.get("checked", False)
                text    = "".join(
                    rt.get("plain_text", "") for rt in td.get("rich_text", [])
                ).strip()
                if text and not checked:
                    # Best-effort assignee detection from trailing "→ Name" or "assigned to Name"
                    assignee = _parse_assignee(text)
                    items.append({
                        "task":     text,
                        "assignee": assignee,
                        "meeting":  title,
                        "date":     date_str,
                        "url":      f"https://notion.so/{page_id.replace('-', '')}",
                    })

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return items


def _parse_assignee(text: str) -> str:
    import re
    for pattern in [
        r"→\s*(.+)$",
        r"—\s*assigned to\s+(.+?)(?:\s*\||\s*$)",
        r"assigned to\s+(.+?)(?:\s*\||\s*$)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


# ── Classify & organise ───────────────────────────────────────────────────────

def _is_mine(item: dict) -> bool:
    assignee = item.get("assignee", "").lower()
    return ME_NAME.lower() in assignee or ME_EMAIL.lower() in assignee or assignee == ""


def _project_label(meeting_title: str) -> str:
    title = meeting_title.lower()
    if "highradius" in title or "cfp" in title or "commercial fire" in title:
        return "HighRadius | Commercial Fire Protection"
    if "anthony" in title or "broussard" in title:
        return "AI Training — Anthony Broussard"
    if "kevin" in title or "chandler" in title:
        return "AI Training — Kevin Chandler"
    if "franco" in title or "cinquini" in title:
        return "AI Training — Franco Cinquini"
    if "leonel" in title or "arrieta" in title:
        return "AI Training — Leonel Arrieta"
    if "valcourt" in title or "luis morales" in title:
        return "AI Training — Valcourt"
    if "carlos" in title and ("diaz" in title or "alberto" in title):
        return "AI Training — Carlos Alberto Díaz"
    if "kevin" in title or "chandler" in title:
        return "AI Training — Kevin Chandler"
    if "cynthia" in title or "nacianceno" in title:
        return "AI Training — Cynthia Nacianceno"
    if "isaias" in title or "matancillas" in title:
        return "AI Training — Isaias Matancillas"
    if "berhat" in title:
        return "AI Training — Berhat Construction"
    if "daniel morales" in title or "gerardo morales" in title or "morales" in title:
        return "AI Training — Gerardo Morales (Manufacturing)"
    if "victor" in title or "robles" in title:
        return "Partnership — Victor Robles"
    if "syncron" in title or "daniel garcía" in title or "daniel garcia" in title:
        return "Partnership — Syncron (Daniel García)"
    if "david lozano" in title:
        return "CEMEX — AP / P2P (David Lozano)"
    if "cemex" in title or "o2c" in title or "alpha cadence" in title or "p2p" in title or "f2f" in title:
        return "CEMEX — Process Transformation"
    if "lsu" in title or "alejandra" in title or "guzman" in title:
        return "LSU HealthCare — Process Mapping"
    if "biweekly" in title or "tracie" in title or "tessier" in title:
        return "CEMEX — Biweekly with Tracie"
    if "rm operative" in title:
        return "CEMEX — RM Operative Support"
    if "weekly ap" in title:
        return "CEMEX — Weekly AP Summary"
    return "Other"


def group_by_project(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        label = _project_label(item["meeting"])
        grouped.setdefault(label, []).append(item)
    return dict(sorted(grouped.items()))


# ── Email rendering ───────────────────────────────────────────────────────────

CSS = """
body{font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;max-width:820px;margin:0 auto;padding:16px}
h1{color:#1a56db;border-bottom:2px solid #1a56db;padding-bottom:8px}
h2{color:#2563eb;margin-top:28px}
h3{color:#374151;margin-top:16px;margin-bottom:6px;font-size:14px;
   border-left:3px solid #6b7280;padding-left:8px}
.mine{background:#eff6ff;border-left:4px solid #1a56db;border-radius:6px;padding:14px;margin-bottom:14px}
.others{background:#f0fdf4;border-left:4px solid #16a34a;border-radius:6px;padding:14px;margin-bottom:14px}
ul{margin:6px 0;padding-left:20px}
li{margin-bottom:4px;line-height:1.5}
.em{color:#6b7280;font-style:italic}
.footer{color:#9ca3af;font-size:12px;margin-top:32px;border-top:1px solid #e5e7eb;padding-top:12px}
table.summary{background:#1a56db;color:white;border-radius:8px;margin-bottom:24px;
              width:100%;border-spacing:0;padding:4px 0}
td.stat{padding:10px 28px;text-align:center}
td.divider{border-left:1px solid rgba(255,255,255,.3)}
.num{font-size:28px;font-weight:bold;display:block}
.lbl{font-size:12px}
"""


def _section_html(title: str, items: list[dict], css_class: str) -> str:
    if not items:
        return ""
    rows = ""
    for it in items:
        task     = it["task"]
        assignee = it.get("assignee", "")
        date     = it.get("date", "")
        url      = it.get("url", "")
        link     = f'<a href="{url}" style="color:inherit;">🔗</a> ' if url else ""
        note     = f' <span class="em">→ {assignee}</span>' if assignee else ""
        date_tag = f' <span class="em">({date})</span>' if date else ""
        rows    += f"<li>{link}{task}{note}{date_tag}</li>\n"
    return f'<div class="{css_class}"><h3>{title}</h3><ul>{rows}</ul></div>'


def build_html(my_items: list[dict], other_items: list[dict], today: str) -> str:
    my_grouped    = group_by_project(my_items)
    other_grouped = group_by_project(other_items)

    my_html    = "".join(_section_html(proj, items, "mine")   for proj, items in my_grouped.items())
    other_html = "".join(_section_html(proj, items, "others") for proj, items in other_grouped.items())

    if not my_html:
        my_html = "<p style='color:#6b7280;'>No open action items found for you. 🎉</p>"
    if not other_html:
        other_html = "<p style='color:#6b7280;'>No open items found waiting on others.</p>"

    return f"""<!DOCTYPE html><html><head><style>{CSS}</style></head><body>
<h1>📋 Daily Action Items Digest</h1>
<p style="color:#6b7280;">{today} · Sources: Fathom + Notion</p>

<table class="summary">
<tr>
  <td class="stat"><span class="num">{len(my_items)}</span><span class="lbl">Your action items</span></td>
  <td class="stat divider"><span class="num">{len(other_items)}</span><span class="lbl">Waiting on others</span></td>
</tr>
</table>

<h2>✅ Your Action Items</h2>
{my_html}

<h2>⏳ Waiting on Others</h2>
{other_html}

<div class="footer">
  🤖 Auto-generated from Fathom + Notion · Fidaris Advisory ·
  <a href="mailto:{ME_EMAIL}">{ME_EMAIL}</a>
</div>
</body></html>"""


# ── Send email ────────────────────────────────────────────────────────────────

def send_email(subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = DIGEST_RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, DIGEST_RECIPIENT, msg.as_string())
    print(f"✓ Email sent to {DIGEST_RECIPIENT}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    since = datetime.datetime.utcnow() - datetime.timedelta(days=LOOKBACK_DAYS)
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")

    print(f"Fetching meetings since {since.date()} …")

    fathom_items = []
    notion_items = []

    try:
        fathom_items = fetch_fathom_action_items(since)
        print(f"  Fathom: {len(fathom_items)} action items")
    except Exception as e:
        print(f"  Fathom error: {e}")

    try:
        notion_items = fetch_notion_action_items(since)
        print(f"  Notion: {len(notion_items)} action items")
    except Exception as e:
        print(f"  Notion error: {e}")

    all_items   = fathom_items + notion_items
    my_items    = [i for i in all_items if _is_mine(i)]
    other_items = [i for i in all_items if not _is_mine(i)]

    # Deduplicate by task text (Notion often mirrors Fathom)
    def dedup(items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for it in items:
            key = it["task"][:80].lower()
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out

    my_items    = dedup(my_items)
    other_items = dedup(other_items)

    html    = build_html(my_items, other_items, today)
    subject = f"📋 Daily Action Items Digest — {today}"

    send_email(subject, html)


if __name__ == "__main__":
    main()
