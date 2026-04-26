"""Pydantic models for Gemini tool calls."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AddEventArgs(BaseModel):
    """Arguments for the add_event tool call."""

    title: str
    start_time: str = Field(..., description="ISO 8601 datetime string, or YYYY-MM-DD for all-day events")
    end_time: str = Field(..., description="ISO 8601 datetime string, or YYYY-MM-DD exclusive end for all-day events")
    location: str | None = None
    is_all_day: bool = False


class EditEventArgs(BaseModel):
    """Arguments for the edit_event tool call."""

    event_id: str = Field(..., description="Google Calendar event ID to modify")
    title: str | None = None
    start_time: str | None = Field(default=None, description="ISO 8601 datetime string, or YYYY-MM-DD for all-day events")
    end_time: str | None = Field(default=None, description="ISO 8601 datetime string, or YYYY-MM-DD exclusive end for all-day events")
    location: str | None = None
    is_all_day: bool = False


class DeleteEventArgs(BaseModel):
    """Arguments for the delete_event tool call."""

    event_id: str = Field(..., description="Google Calendar event ID to delete")


class ToolCall(BaseModel):
    """A single structured function call returned by Gemini."""

    function_name: Literal["add_event", "edit_event", "delete_event"]
    args: AddEventArgs | EditEventArgs | DeleteEventArgs
