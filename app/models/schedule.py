"""Pydantic models for the /schedule/process endpoint payload."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    """A blocked-off time window (24-hour HH:MM strings)."""

    start: str = Field(..., examples=["09:00"], description="Start time in HH:MM (24-hour)")
    end: str = Field(..., examples=["10:00"], description="End time in HH:MM (24-hour)")


class UserPreferences(BaseModel):
    """Scheduling preferences persisted per user."""

    break_time: int = Field(
        ...,
        ge=0,
        description="Minimum free minutes to leave between consecutive events/tasks.",
    )
    context_switch: bool = Field(
        ...,
        description="Whether to avoid context switching by grouping task blocks.",
    )
    burnout: int = Field(
        ...,
        description=(
            "Maximum time in minutes that a task should be scheduled for consecutively."
        ),
    )
    no_work_time: list[TimeRange] = Field(
        default_factory=list,
        description="Time windows that must remain free (no events or tasks scheduled).",
    )


class CalendarEvent(BaseModel):
    """A time-bound calendar entry (meeting, appointment, etc.)."""

    event_id: str | None = Field(
        default=None,
        description="Google Calendar event ID. None if this is a new event not yet on GCal.",
    )
    title: str
    start: str = Field(..., description="ISO 8601 datetime string, e.g. 2026-04-25T09:00:00")
    end: str = Field(..., description="ISO 8601 datetime string, e.g. 2026-04-25T10:00:00")
    location: str | None = None
    attendees: list[str] | None = None
    is_all_day: bool = False


class ScheduleRequest(BaseModel):
    """The four-field payload sent by the frontend when the user hits 'submit'."""

    date: str = Field(
        ...,
        description="Target date in YYYY-MM-DD format.",
        examples=["2026-04-25"],
    )
    timezone: str = Field(
        ...,
        description="User's local IANA timezone, e.g. 'America/Los_Angeles'.",
    )
    todos: list[str] = Field(
        default_factory=list,
        description="List of natural language todos from the user.",
    )
    preferences: UserPreferences = Field(
        ...,
        description="User's scheduling preferences for this session.",
    )
