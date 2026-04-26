"""Google Calendar API wrapper — all operations on the primary calendar."""
from __future__ import annotations

from datetime import datetime, timezone

import googleapiclient.discovery
from google.oauth2.credentials import Credentials

from app.models.gemini import AddEventArgs, EditEventArgs
from app.models.schedule import CalendarEvent


def _build_service(credentials: Credentials):
    """Build and return an authorised Google Calendar API service client."""
    return googleapiclient.discovery.build(
        "calendar", "v3", credentials=credentials, cache_discovery=False
    )


def _parse_event(raw: dict) -> CalendarEvent:
    """Convert a raw GCal API event dict into a CalendarEvent Pydantic model."""
    start = raw.get("start", {})
    end = raw.get("end", {})

    # GCal returns dateTime for timed events, date for all-day events
    start_str = start.get("dateTime") or start.get("date", "")
    end_str = end.get("dateTime") or end.get("date", "")
    is_all_day = "date" in start and "dateTime" not in start

    return CalendarEvent(
        event_id=raw.get("id"),
        title=raw.get("summary", "(No title)"),
        start=start_str,
        end=end_str,
        location=raw.get("location"),
        is_all_day=is_all_day,
    )


async def get_events_for_date(
    credentials: Credentials, date: str
) -> list[CalendarEvent]:
    """
    Fetch all primary-calendar events for a given date (YYYY-MM-DD).

    Returns events sorted by start time.
    """
    service = _build_service(credentials)

    # Build RFC3339 window for the full day in UTC
    time_min = f"{date}T00:00:00Z"
    time_max = f"{date}T23:59:59Z"

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [_parse_event(item) for item in result.get("items", [])]


async def add_event(credentials: Credentials, args: AddEventArgs, timezone: str) -> str:
    """
    Insert a new event into the primary calendar.

    Returns the new event's GCal event_id.
    """
    service = _build_service(credentials)

    body: dict = {
        "summary": args.title,
        "start": {"dateTime": args.start_time, "timeZone": timezone},
        "end": {"dateTime": args.end_time, "timeZone": timezone},
    }
    if args.location:
        body["location"] = args.location

    created = service.events().insert(calendarId="primary", body=body).execute()
    return created.get("id", "")


async def edit_event(
    credentials: Credentials, event_id: str, args: EditEventArgs, timezone: str
) -> None:
    """Patch an existing primary-calendar event with only the provided fields."""
    service = _build_service(credentials)

    patch_body: dict = {}
    if args.title is not None:
        patch_body["summary"] = args.title
    if args.start_time is not None:
        patch_body["start"] = {"dateTime": args.start_time, "timeZone": timezone}
    if args.end_time is not None:
        patch_body["end"] = {"dateTime": args.end_time, "timeZone": timezone}
    if args.location is not None:
        patch_body["location"] = args.location

    if patch_body:
        service.events().patch(
            calendarId="primary", eventId=event_id, body=patch_body
        ).execute()


async def delete_event(credentials: Credentials, event_id: str) -> None:
    """Delete an event from the primary calendar by its event_id."""
    service = _build_service(credentials)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
