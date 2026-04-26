"""Google Calendar API wrapper — all operations on the primary calendar."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import zoneinfo

import googleapiclient.discovery
from google.oauth2.credentials import Credentials

from app.models.ai import AddEventArgs, EditEventArgs
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

    # Extract attendee emails, excluding the user themselves
    attendees = [
        a.get("email") 
        for a in raw.get("attendees", []) 
        if a.get("email") and not a.get("self")
    ]

    return CalendarEvent(
        event_id=raw.get("id"),
        title=raw.get("summary", "(No title)"),
        start=start_str,
        end=end_str,
        location=raw.get("location"),
        attendees=attendees if attendees else None,
        is_all_day=is_all_day,
    )


async def get_events_for_date(
    credentials: Credentials, date: str, timezone: str
) -> list[CalendarEvent]:
    """
    Fetch all primary-calendar events for a given date (YYYY-MM-DD).

    Returns events sorted by start time.
    """
    service = _build_service(credentials)

    # Build RFC3339 window for the full day in the user's specific timezone
    tz = zoneinfo.ZoneInfo(timezone)
    start_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
    end_dt = start_dt.replace(hour=23, minute=59, second=59)

    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

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

    is_all_day = args.is_all_day or (bool(args.start_time) and len(args.start_time) == 10)

    if is_all_day:
        start_date = args.start_time[:10]
        end_date = args.end_time[:10] if args.end_time else (
            date.fromisoformat(start_date) + timedelta(days=1)
        ).isoformat()
        # Ensure end is always the day after start for single-day all-day events
        if end_date == start_date:
            end_date = (date.fromisoformat(start_date) + timedelta(days=1)).isoformat()
        body: dict = {
            "summary": args.title,
            "start": {"date": start_date},
            "end": {"date": end_date},
        }
    else:
        body = {
            "summary": args.title,
            "start": {"dateTime": args.start_time, "timeZone": timezone},
            "end": {"dateTime": args.end_time, "timeZone": timezone},
        }

    if args.location:
        body["location"] = args.location
        
    if args.attendees:
        body["attendees"] = [{"email": email} for email in args.attendees if "@" in email]

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

    is_all_day = args.is_all_day or (bool(args.start_time) and len(args.start_time) == 10)

    if is_all_day:
        if args.start_time is not None:
            start_date = args.start_time[:10]
            patch_body["start"] = {"date": start_date}
            if args.end_time is not None:
                end_date = args.end_time[:10]
                if end_date == start_date:
                    end_date = (date.fromisoformat(start_date) + timedelta(days=1)).isoformat()
            else:
                end_date = (date.fromisoformat(start_date) + timedelta(days=1)).isoformat()
            patch_body["end"] = {"date": end_date}
    else:
        # If modifying times for a timed event, we should provide both to avoid 400s 
        # when converting an all-day event to a timed event.
        if args.start_time is not None or args.end_time is not None:
            st = args.start_time
            et = args.end_time
            if st is not None and et is None:
                try:
                    et = (datetime.fromisoformat(st) + timedelta(hours=1)).isoformat()
                except Exception:
                    et = st
            elif et is not None and st is None:
                try:
                    st = (datetime.fromisoformat(et) - timedelta(hours=1)).isoformat()
                except Exception:
                    st = et

            patch_body["start"] = {"dateTime": st, "timeZone": timezone}
            patch_body["end"] = {"dateTime": et, "timeZone": timezone}

    if args.location is not None:
        patch_body["location"] = args.location
        
    if args.attendees is not None:
        patch_body["attendees"] = [{"email": email} for email in args.attendees if "@" in email]

    if patch_body:
        service.events().patch(
            calendarId="primary", eventId=event_id, body=patch_body
        ).execute()


async def delete_event(credentials: Credentials, event_id: str) -> None:
    """Delete an event from the primary calendar by its event_id."""
    service = _build_service(credentials)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
