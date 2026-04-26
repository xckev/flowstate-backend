"""Pydantic models for API responses."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ProcessResult(BaseModel):
    """Response returned after processing a ScheduleRequest."""

    message: str
