import base64
import os
import re

from googleapiclient.discovery import build

CLIENT_KEYWORDS = {
    "CEMEX":       ["cemex", "rmx", "concreto"],
    "CFP":         ["cfp", "commercial fire", "highradius", "fire protection"],
    "DEACERO":     ["deacero", "acero"],
    "AI_TRAINING": ["ai training", "entrenamiento ia"],
}

CROSS_CLIENT_TERMS = {
    "CEMEX":       ["deacero", "cfp", "commercial fire", "highradius"],
    "CFP":         ["cemex", "rmx", "deacero"],
    "DEACERO":     ["cemex", "rmx", "cfp", "commercial fire"],
    "AI_TRAINING": ["cemex", "rmx", "deacero", "cfp", "commercial fire", "highradius"],
}


def detect_client(meeting: dict) -> str:
    """Detect which client this meeting is about from title, description, and attendee emails."""
    text = (
        meeting.get("summary", "") + " " +
        meeting.get("description", "") + " " +
        " ".join(a.get("email", "") for a in meeting.get("attendees", []))
    ).lower()
    for client, keywords in CLIENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return client
    return ""


def _extract_key_terms(meeting: dict) -> list:
    """Extract significant words from the meeting title."""
    stopwords = {"the", "and", "for", "with", "from", "that", "this", "are", "was",
                 "its", "at", "in", "on", "a", "an", "of", "to", "by"}
    words = re.sub(r"[^\w\s]", " ", meeting.get("summary", "")).split()
    return [w for w in words if len(w) > 3 and w.lower() not in stopwords]


def _is_relevant(text: str, client: str) -> bool:
    """Return False if text clearly belongs to a different client."""
    if not client:
        return True
    text_lower = text.lower()
    for term in CROSS_CLIENT_TERMS.get(client, []):
        if term in text_lower:
            return False
    return True


def _build_gmail_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _extract_email_text(message: dict, max_chars: int = 2000) -> str:
    """Extract plain text body from a Gmail message payload."""
    def _get_parts(payload):
        parts = []
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                parts.append(decoded)
        for part in payload.get("parts", []):
            parts.extend(_get_parts(part))
        return parts

    texts = _get_parts(message.get("payload", {}))
    return "\n".join(texts)[:max_chars]


def _fetch_messages(service, query: str, seen_ids: set, results: list,
                    max_results: int = 8, client: str = "") -> None:
    """Execute a Gmail search and append deduplicated, client-filtered metadata results."""
    try:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        for msg in resp.get("messages", []):
            if msg["id"] in seen_ids:
                continue
            seen_ids.add(msg["id"])
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "")
            snippet = data.get("snippet", "")
            if not _is_relevant(subject + " " + snippet, client):
                continue
            results.append({
                "from": headers.get("From", ""),
                "subject": subject,
                "date": headers.get("Date", ""),
                "snippet": snippet[:300],
            })
    except Exception as e:
        print(f"Gmail search error ({query[:70]}): {e}")


def search_gmail_for_meeting(credentials, meeting: dict, user_email: str) -> list:
    """Search Gmail for emails related to this meeting's attendees, client, and topic."""
    service = _build_gmail_service(credentials)
    seen_ids: set = set()
    results: list = []
    client = detect_client(meeting)
    key_terms = _extract_key_terms(meeting)

    attendees = [
        a["email"] for a in meeting.get("attendees", [])
        if a.get("email", "").lower() != user_email.lower()
    ]

    # 1. Attendee email threads (90 days)
    for email_addr in attendees[:5]:
        query = f"(from:{email_addr} OR to:{email_addr}) newer_than:90d"
        _fetch_messages(service, query, seen_ids, results, max_results=8, client=client)

    # 2. Meeting title keywords in subject (90 days)
    if key_terms:
        kw_query = " OR ".join(f'"{t}"' for t in key_terms[:4])
        query = f"subject:({kw_query}) newer_than:90d"
        _fetch_messages(service, query, seen_ids, results, max_results=8, client=client)

    # 3. Client name + key terms in body — catches threads not caught by attendee search
    if client and key_terms:
        body_terms = " ".join(f'"{t}"' for t in key_terms[:3])
        query = f'"{client}" {body_terms} newer_than:90d'
        _fetch_messages(service, query, seen_ids, results, max_results=6, client=client)

    return results


def search_fathom_for_meeting(credentials, meeting: dict) -> list:
    """Search the Fathom Gmail label for past meeting notes related to this meeting."""
    service = _build_gmail_service(credentials)
    seen_ids: set = set()
    results: list = []
    client = detect_client(meeting)

    # Build attendee name terms
    attendee_terms = []
    for attendee in meeting.get("attendees", [])[:5]:
        name = attendee.get("name", "")
        email = attendee.get("email", "")
        if name and "@" not in name:
            parts = name.strip().split()
            if parts:
                attendee_terms.append(parts[-1])   # last name (most distinctive)
            if len(parts) > 1:
                attendee_terms.append(parts[0])    # first name as backup
        elif email:
            local = email.split("@")[0]
            if len(local) > 3:
                attendee_terms.append(local)

    # Build queries: prefer attendee name + client (precise), then each alone
    queries = []
    if attendee_terms and client:
        for term in attendee_terms[:3]:
            queries.append(f'label:Fathom "{term}" "{client}"')
        for term in attendee_terms[:2]:
            queries.append(f'label:Fathom "{term}"')
    elif attendee_terms:
        for term in attendee_terms[:4]:
            queries.append(f'label:Fathom "{term}"')
    if client:
        queries.append(f'label:Fathom "{client}"')

    for query in queries[:6]:
        try:
            resp = service.users().messages().list(
                userId="me", q=query, maxResults=5
            ).execute()
            for msg in resp.get("messages", []):
                if msg["id"] in seen_ids:
                    continue
                seen_ids.add(msg["id"])
                data = service.users().messages().get(
                    userId="me", id=msg["id"], format="full"
                ).execute()
                headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "")
                body = _extract_email_text(data, max_chars=2000)
                if not _is_relevant(subject + " " + body[:500], client):
                    print(f"  Fathom: skipping cross-client result: {subject[:60]}")
                    continue
                results.append({
                    "subject": subject,
                    "date": headers.get("Date", ""),
                    "body": body or data.get("snippet", "")[:500],
                })
                print(f"  Fathom note found: {subject[:60]}")
        except Exception as e:
            print(f"Fathom search error ({query[:60]}): {e}")

    print(f"  Fathom: {len(results)} relevant note(s) found")
    return results


def search_notion_for_meeting(meeting: dict) -> list:
    """Search Notion for pages related to this meeting by title and client context."""
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        return []

    try:
        from notion_client import Client
        notion_client = Client(auth=token)
    except ImportError:
        return []

    client = detect_client(meeting)
    key_terms = _extract_key_terms(meeting)
    title = meeting.get("summary", "").strip()

    # Queries from most-specific to least-specific
    queries = []
    if title:
        queries.append(title)
    if client and key_terms:
        queries.append(f"{client} {' '.join(key_terms[:3])}")
    if client:
        queries.append(client)

    seen_urls: set = set()
    pages: list = []

    for query in queries[:4]:
        try:
            results = notion_client.search(
                query=query,
                filter={"property": "object", "value": "page"},
                page_size=8,
            ).get("results", [])

            for page in results:
                url = page.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                props = page.get("properties", {})
                page_title = ""
                for prop in props.values():
                    if prop.get("type") == "title":
                        page_title = "".join(
                            t.get("plain_text", "") for t in prop.get("title", [])
                        )
                        break
                if not _is_relevant(page_title, client):
                    continue
                pages.append({
                    "title": page_title or "Untitled",
                    "url": url,
                    "last_edited": page.get("last_edited_time", "")[:10],
                })
        except Exception as e:
            print(f"Notion search error ({query}): {e}")

    return pages


def research_meeting(credentials, meeting: dict) -> dict:
    """Gather all context for a meeting from Gmail inbox, Fathom notes, and Notion."""
    user_email = os.environ.get("USER_EMAIL", os.environ.get("RECIPIENT_EMAIL", ""))
    client = detect_client(meeting)
    if client:
        print(f"  Detected client context: {client}")
    else:
        print("  No specific client detected — broad search mode")

    print("  Searching Gmail for relevant emails...")
    emails = search_gmail_for_meeting(credentials, meeting, user_email)
    print(f"  Found {len(emails)} relevant email(s)")

    print("  Searching Fathom folder for past meeting notes...")
    fathom_notes = search_fathom_for_meeting(credentials, meeting)

    print("  Searching Notion for relevant notes and pages...")
    notion_pages = search_notion_for_meeting(meeting)
    print(f"  Found {len(notion_pages)} Notion page(s)")

    return {
        "emails": emails,
        "fathom_notes": fathom_notes,
        "notion_pages": notion_pages,
        "detected_client": client,
    }
