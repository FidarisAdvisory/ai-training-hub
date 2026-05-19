import datetime
import math
import os
import re

MONTHLY_TARGET = 17_000.0
AVG_AI_TRAINING = 420.0
PREMIUM_RATE = 125.0

HOURLY_RATES = {
    "CEMEX":   125.0,
    "CFP":     125.0,
    "DEACERO":  82.0,
}

TIME_LOG_DATABASES = {
    "CEMEX":   "078eca46-ef5f-4602-9c56-37887a43b670",
    "CFP":     "8494fb0a-b831-4063-84c5-346f96d4ca8c",
    "DEACERO": "0f697f8a-e3b9-4f48-8fd9-1c98d5fdf3b4",
}

AI_LEADS_CRM_ID = "b285e78b-ede5-4b0a-8798-126b86fa58e6"


def get_monthly_revenue(credentials=None) -> dict:
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        print("[REVENUE] NOTION_API_TOKEN is not set — skipping revenue data.")
        return {}

    print(f"[REVENUE] NOTION_API_TOKEN is set (length: {len(token)})")

    try:
        from notion_client import Client
        notion = Client(auth=token)
    except ImportError:
        print("[REVENUE] notion-client package not installed.")
        return {}

    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    if today.month == 12:
        month_end_date = today.replace(year=today.year + 1, month=1, day=1) - datetime.timedelta(days=1)
    else:
        month_end_date = today.replace(month=today.month + 1, day=1) - datetime.timedelta(days=1)
    month_end = month_end_date.isoformat()
    days_in_month = month_end_date.day
    month_name = today.strftime("%B %Y")

    print(f"[REVENUE] Querying for {month_name} ({month_start} to {month_end})")

    client_revenue = {}
    total_hourly = 0.0
    access_errors = []

    for client_name, db_id in TIME_LOG_DATABASES.items():
        rate = HOURLY_RATES[client_name]
        print(f"[REVENUE] Querying {client_name} (db: {db_id})...")
        try:
            response = notion.databases.query(
                database_id=db_id,
                page_size=100,
                filter={
                    "and": [
                        {"property": "Date", "date": {"on_or_after": month_start}},
                        {"property": "Date", "date": {"on_or_before": month_end}},
                        {"property": "Billable", "checkbox": {"equals": True}},
                    ]
                },
                sorts=[{"property": "Date", "direction": "descending"}],
            )
            total_hours, last_entry = _sum_hours_and_last(response)
            print(f"[REVENUE]   {client_name}: {len(response.get('results', []))} entries, {total_hours:.1f} hrs, last: {last_entry}")

            while response.get("has_more"):
                response = notion.databases.query(
                    database_id=db_id, page_size=100,
                    filter={
                        "and": [
                            {"property": "Date", "date": {"on_or_after": month_start}},
                            {"property": "Date", "date": {"on_or_before": month_end}},
                            {"property": "Billable", "checkbox": {"equals": True}},
                        ]
                    },
                    start_cursor=response["next_cursor"],
                )
                h, ld = _sum_hours_and_last(response)
                total_hours += h
                if ld and (not last_entry or ld > last_entry):
                    last_entry = ld

            revenue = round(total_hours * rate, 2)
            total_hourly += revenue
            client_revenue[client_name] = {
                "hours": round(total_hours, 1),
                "rate": rate,
                "revenue": revenue,
                "last_entry": last_entry,
            }
            print(f"[REVENUE]   {client_name}: {total_hours:.1f} hrs x ${rate} = ${revenue:.2f}")

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            print(f"[REVENUE] ERROR querying {client_name}: {err_msg}")
            access_errors.append(f"{client_name} ({err_msg})")
            client_revenue[client_name] = {"hours": 0.0, "rate": rate, "revenue": 0.0, "last_entry": ""}

    print(f"[REVENUE] Total hourly: ${total_hourly:.2f}")

    # Google Drive SOW search
    sow_data = {"sows": [], "total": 0.0}
    if credentials is not None:
        sow_data = _get_sow_revenue(credentials)
    else:
        print("[REVENUE] No Google credentials provided — skipping Drive SOW search.")

    total_mtd = round(total_hourly + sow_data["total"], 2)

    # Pacing math
    gap = max(0.0, MONTHLY_TARGET - total_mtd)
    days_remaining = max(1, days_in_month - today.day + 1)
    daily_needed = round(gap / days_remaining, 2)
    hours_per_day = round(gap / PREMIUM_RATE / days_remaining, 1)
    trainings_needed = math.ceil(gap / AVG_AI_TRAINING) if gap > 0 else 0
    expected_pct = round(today.day / days_in_month * 100)
    actual_pct = round(total_mtd / MONTHLY_TARGET * 100)

    if actual_pct >= 100:
        status = "Target hit"
    elif actual_pct >= expected_pct - 5:
        status = "On pace"
    elif actual_pct >= expected_pct - 15:
        status = "Behind pace"
    else:
        status = "Off pace"

    print(f"[REVENUE] MTD: ${total_mtd} ({actual_pct}% of target, expected {expected_pct}%) — {status}")

    print("[REVENUE] Querying AI Leads CRM...")
    pipeline = _get_pipeline(notion)
    print(f"[REVENUE] Pipeline: ${pipeline.get('total_value', 0):.2f} across {pipeline.get('active_count', 0)} leads")

    result = {
        "month": month_name,
        "clients": client_revenue,
        "total_hourly": round(total_hourly, 2),
        "sow_revenue": sow_data["total"],
        "sows": sow_data["sows"],
        "total_mtd": total_mtd,
        "monthly_target": MONTHLY_TARGET,
        "gap": round(gap, 2),
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "day_of_month": today.day,
        "daily_needed": daily_needed,
        "hours_per_day": hours_per_day,
        "trainings_needed": trainings_needed,
        "expected_pct": expected_pct,
        "actual_pct": actual_pct,
        "status": status,
        "pipeline": pipeline,
    }
    if access_errors:
        result["access_errors"] = access_errors
    return result


def _sum_hours_and_last(response: dict) -> tuple:
    total = 0.0
    last_date = ""
    for page in response.get("results", []):
        props = page.get("properties", {})
        h = props.get("Hours", {})
        if h.get("type") == "number" and h.get("number") is not None:
            total += h["number"]
        date_val = ((props.get("Date") or {}).get("date") or {}).get("start", "")
        if date_val and (not last_date or date_val > last_date):
            last_date = date_val
    return total, last_date


def _get_sow_revenue(credentials) -> dict:
    """Search Google Drive for AI training SOW files and extract total fees."""
    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=credentials)
    except Exception as e:
        print(f"[REVENUE] Drive API build failed: {type(e).__name__}: {e}")
        return {"sows": [], "total": 0.0}

    query = (
        "name contains 'SOW' and ("
        "name contains 'AI' or name contains 'training' or name contains 'Training' or "
        "name contains 'capacitación' or name contains 'Capacitación'"
        ")"
    )
    try:
        results = service.files().list(
            q=query,
            pageSize=50,
            fields="files(id, name, modifiedTime, mimeType)",
            orderBy="modifiedTime desc",
        ).execute()
        files = results.get("files", [])
        print(f"[REVENUE] Drive: found {len(files)} SOW files")
    except Exception as e:
        print(f"[REVENUE] Drive search failed: {type(e).__name__}: {e}")
        return {"sows": [], "total": 0.0}

    # Deduplicate by lowercase filename
    seen: dict = {}
    for f in files:
        key = f["name"].lower().strip()
        if key not in seen:
            seen[key] = f

    sows = []
    total = 0.0
    for f in seen.values():
        text = _export_doc_text(service, f["id"], f["mimeType"])
        fee = _parse_sow_fee(text + " " + f["name"])
        client = _parse_sow_client(f["name"], text)
        print(f"[REVENUE]   SOW: {f['name'][:60]} → client={client}, fee=${fee}")
        if fee > 0:
            sows.append({"client": client, "file": f["name"], "fee": fee})
            total += fee

    return {"sows": sows, "total": round(total, 2)}


def _export_doc_text(service, file_id: str, mime_type: str, max_chars: int = 1500) -> str:
    try:
        if mime_type == "application/vnd.google-apps.document":
            content = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            return content.decode("utf-8", errors="ignore")[:max_chars]
    except Exception:
        pass
    return ""


def _parse_sow_fee(text: str) -> float:
    patterns = [
        r"Total Engagement Fee[^\$]*\$\s*([\d,]+(?:\.\d{2})?)",
        r"Honorarios Totales del Programa[^\$]*\$\s*([\d,]+(?:\.\d{2})?)",
        r"Monto Total del Programa[^\$]*\$\s*([\d,]+(?:\.\d{2})?)",
        r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:USD)?",
    ]
    best = 0.0
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            amounts = []
            for m in matches:
                try:
                    amounts.append(float(m.replace(",", "")))
                except ValueError:
                    pass
            if amounts:
                val = max(amounts)
                if i < 3:
                    return val
                best = max(best, val)
    return best


def _parse_sow_client(filename: str, text: str = "") -> str:
    for pattern in [r"Prepared for:\s*([^|\n]+)\|", r"Preparado para:\s*([^|\n]+)\|"]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    name = filename
    for ext in (".docx", ".pdf", ".doc", ".gdoc"):
        name = name.replace(ext, "")
    name = re.sub(r"SOW[-_\s]*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"AI[-_\s]*[Tt]raining[-_\s]*", "", name, flags=re.IGNORECASE)
    return name.strip()[:50]


def _get_pipeline(notion) -> dict:
    try:
        response = notion.databases.query(
            database_id=AI_LEADS_CRM_ID,
            page_size=100,
            filter={
                "and": [
                    {"property": "Stage", "select": {"does_not_equal": "Lost"}},
                    {"property": "Stage", "select": {"does_not_equal": "Completed"}},
                    {"property": "Stage", "select": {"does_not_equal": "Training completed"}},
                ]
            },
        )
        print(f"[REVENUE]   CRM returned {len(response.get('results', []))} active leads")

        total_value = 0.0
        active_count = 0
        hot_leads = []

        for page in response.get("results", []):
            props = page.get("properties", {})
            revenue_val = (props.get("Revenue") or {}).get("number") or 0
            total_value += revenue_val
            active_count += 1

            name = "".join(t.get("plain_text", "") for t in (props.get("Name") or {}).get("title", []))
            stage = ((props.get("Stage") or {}).get("select") or {}).get("name", "")
            priority = ((props.get("Priority") or {}).get("select") or {}).get("name", "")
            next_action = "".join(t.get("plain_text", "") for t in (props.get("Next Action") or {}).get("rich_text", []))
            next_action_date = ((props.get("Next Action Date") or {}).get("date") or {}).get("start", "")
            company = "".join(t.get("plain_text", "") for t in (props.get("Company") or {}).get("rich_text", []))

            if priority == "High":
                hot_leads.append({
                    "name": name,
                    "company": company,
                    "stage": stage,
                    "revenue": revenue_val,
                    "next_action": next_action,
                    "next_action_date": next_action_date,
                })

        hot_leads.sort(key=lambda x: x.get("next_action_date") or "9999")
        return {
            "total_value": round(total_value, 2),
            "active_count": active_count,
            "hot_leads": hot_leads[:5],
        }

    except Exception as e:
        print(f"[REVENUE] ERROR querying AI Leads CRM: {type(e).__name__}: {e}")
        return {"total_value": 0.0, "active_count": 0, "hot_leads": []}
