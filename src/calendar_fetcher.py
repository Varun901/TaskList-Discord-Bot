from __future__ import annotations
"""
calendar_fetcher.py
──────────────────
Fetches tasks/events from Google Calendar (public iCal feed) or Notion
(public database via the Notion API).

All functions are async and return a list of Task dicts:
    {
        "name":        str,
        "due":         Optional[date],
        "description": str,
        "url":         Optional[str],
    }
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any, Optional, Tuple

import httpx
from icalendar import Calendar as iCal

log = logging.getLogger("CalendarFetcher")

# ─── Types ────────────────────────────────────────────────────────────────────

Task = Dict[str, Any]


# ─── Google Calendar ──────────────────────────────────────────────────────────

def _google_ical_url(calendar_id: str) -> str:
    """
    Converts a Google Calendar ID to its public iCal URL.
    Works for:
      - raw calendar IDs  (…@gmail.com  or  …@group.calendar.google.com)
      - already-formed URLs (passed through unchanged)
    """
    if calendar_id.startswith("http"):
        return calendar_id
    encoded = calendar_id.replace("@", "%40")
    return f"https://calendar.google.com/calendar/ical/{encoded}/public/basic.ics"


async def fetch_google_tasks(
    calendar_id: str, target_date: Optional[date] = None
) -> Tuple[bool, str, List[Task]]:
    """
    Fetches events from a *public* Google Calendar iCal feed.
    Returns (success, error_msg, tasks).
    """
    url = _google_ical_url(calendar_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}", []
            cal = iCal.from_ical(resp.content.decode("utf-8", errors="replace"))

        tasks: List[Task] = []
        td = target_date or date.today()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            # Determine event date
            dtstart = component.get("DTSTART")
            if dtstart is None:
                continue
            dt = dtstart.dt
            if isinstance(dt, datetime):
                event_date = dt.date()
            else:
                event_date = dt  # already a date

            if target_date is not None and event_date != td:
                continue

            summary = str(component.get("SUMMARY", "Untitled Event"))
            description = str(component.get("DESCRIPTION", "")) or ""
            url_prop = component.get("URL")
            event_url = str(url_prop) if url_prop else None

            tasks.append(
                {
                    "name": summary,
                    "due": event_date,
                    "description": description.strip(),
                    "url": event_url,
                }
            )

        # Sort by date
        tasks.sort(key=lambda t: t["due"] or date.min)
        return True, "", tasks
    except Exception as exc:
        log.warning(f"fetch_google_tasks error for calendar {calendar_id!r}: {exc}")
        return False, str(exc), []


# ─── Notion ───────────────────────────────────────────────────────────────────

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _extract_date(prop: Dict) -> Optional[date]:
    """Pull a date out of a Notion date property."""
    try:
        raw = prop.get("date") or {}
        start = raw.get("start")
        if not start:
            return None
        # Notion returns ISO 8601; may be date-only or datetime
        if "T" in start:
            return datetime.fromisoformat(start).date()
        return date.fromisoformat(start)
    except Exception:
        return None


def _extract_title(properties: Dict) -> str:
    for key, val in properties.items():
        if val.get("type") == "title":
            parts = val.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts) or "Untitled"
    return "Untitled"


def _extract_rich_text(prop: Dict) -> str:
    parts = prop.get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


async def fetch_notion_tasks(
    database_id: str,
    token: str,
    target_date: Optional[date] = None,
) -> Tuple[bool, str, List[Task]]:
    """
    Fetches pages from a Notion database.
    Filters by any of the common date property names: Date, Due, Due Date, Deadline.
    Returns (success, error_msg, tasks).
    """
    headers = _notion_headers(token)

    # Build filter body
    body: Dict[str, Any] = {"page_size": 100}
    if target_date is not None:
        date_str = target_date.isoformat()
        # Try to filter on common date property names
        body["filter"] = {
            "or": [
                {"property": "Date", "date": {"equals": date_str}},
                {"property": "Due", "date": {"equals": date_str}},
                {"property": "Due Date", "date": {"equals": date_str}},
                {"property": "Deadline", "date": {"equals": date_str}},
            ]
        }

    url = f"{NOTION_API}/databases/{database_id}/query"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 401:
                return False, "Invalid Notion token or database not shared with integration.", []
            if resp.status_code == 404:
                return False, "Notion database not found. Make sure the database ID is correct.", []
            if resp.status_code != 200:
                return False, f"Notion API error {resp.status_code}: {resp.text}", []
            data = resp.json()

        tasks: List[Task] = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            name = _extract_title(props)

            # Find date property
            due_date = None
            for key in ("Date", "Due", "Due Date", "Deadline", "date", "due"):
                if key in props and props[key].get("type") == "date":
                    due_date = _extract_date(props[key])
                    break

            # Description / Notes
            description = ""
            for key in ("Description", "Notes", "Note", "Body", "description", "notes"):
                if key in props and props[key].get("type") == "rich_text":
                    description = _extract_rich_text(props[key])
                    break

            page_url = page.get("url")

            tasks.append(
                {
                    "name": name,
                    "due": due_date,
                    "description": description.strip(),
                    "url": page_url,
                }
            )

        tasks.sort(key=lambda t: t["due"] or date.min)
        return True, "", tasks
    except Exception as exc:
        log.warning(f"fetch_notion_tasks error for database {database_id!r}: {exc}")
        return False, str(exc), []


# ─── Unified entry point ──────────────────────────────────────────────────────

async def fetch_tasks(
    source: str,
    calendar_id: str,
    notion_token: Optional[str],
    target_date: Optional[date] = None,
) -> Tuple[bool, str, List[Task]]:
    if source == "google":
        return await fetch_google_tasks(calendar_id, target_date)
    elif source == "notion":
        if not notion_token:
            return False, "Notion token missing.", []
        return await fetch_notion_tasks(calendar_id, notion_token, target_date)
    else:
        return False, f"Unknown source: {source}", []
