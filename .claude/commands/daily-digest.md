You are generating a daily action items digest for Fidel Salazar (fidelsalazar@fidarisadvisory.com).

Follow these steps exactly:

## Step 1: Identify the current user
Call `get_identity` on the Fathom MCP server to confirm the authenticated user's email.

## Step 2: Fetch Fathom meetings with action items
Call `list_meetings` with:
- `include_action_items: true`
- `include_summary: true`
- `max_pages: 5`
- Filter to meetings from the last 7 days using `created_after` set to 7 days ago

## Step 3: Fetch Notion meeting notes
Call `notion-query-meeting-notes` to get meeting notes from the last 7 days.
For any meeting notes with non-trivial titles or recent activity, call `notion-fetch` on those pages to extract action items from the ACTION ITEMS section.

## Step 4: Compile and organize action items
From all sources, produce two lists:

**List A — Assigned to Fidel Salazar:**
Group by project/client. For each item include the meeting title and date.

**List B — Assigned to Others:**
Group by project/client. For each item include the assignee name, task, meeting title and date.

Exclude items that are clearly already completed or are very old (>30 days) unless they have never appeared in a previous digest.

## Step 5: Create a Gmail draft
Call `create_draft` on the Gmail MCP server with:
- `to: ["fidelsalazar@fidarisadvisory.com"]`
- `subject: "📋 Daily Action Items Digest — {TODAY'S DATE}"`
- `htmlBody`: A well-formatted HTML email with:
  - Section 1: "✅ Action Items Assigned to YOU (Fidel Salazar)" — grouped by project, with meeting date
  - Section 2: "👥 Action Items Assigned to Others" — grouped by project, with assignee name bold and meeting date
  - Footer noting the data sources (Fathom + Notion)

Use clean HTML with inline styles (Arial font, color-coded section headers, bullet lists).

## Important notes
- Today's date is available from the system context
- If no new action items exist for a project, omit that project section
- Flag items from today's meetings prominently
- Do NOT send the email — only create the draft so Fidel can review before sending
