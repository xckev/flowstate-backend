"""Pydantic models for API responses."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChangeResult(BaseModel):
    """The outcome of a single calendar modification."""

    action: Literal["added", "edited", "deleted"]
    event_title: str
    event_id: str | None = None
    error: str | None = None


class ProcessResult(BaseModel):
    """Response returned after processing a ScheduleRequest."""

    date: str
    changes: list[ChangeResult]
    gemini_reasoning: str | None = None
