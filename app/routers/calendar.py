"""Calendar router — read-only access to the user's primary Google Calendar."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbDep
from app.models.schedule import CalendarEvent
from app.services import auth_service, calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get(
    "/events",
    response_model=list[CalendarEvent],
    summary="Fetch primary calendar events for a given date",
)
async def get_events(
    date: str = Query(..., description="Target date in YYYY-MM-DD format", examples=["2026-04-25"]),
    timezone: str = Query(..., description="User's local IANA timezone"),
    current_user: CurrentUser = None,
    db: DbDep = None,
):
    """
    Return all events from the user's primary Google Calendar for the specified date.

    Used by the frontend to show the current calendar state before the user submits.
    """
    credentials = await auth_service.get_credentials(current_user["user_id"], db)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No stored credentials for this user. Please log in again.",
        )

    try:
        events = await calendar_service.get_events_for_date(credentials, date, timezone)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch calendar events: {exc}",
        )

    return events
