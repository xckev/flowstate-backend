"""Gemini 2.5 Pro integration — builds prompt and parses structured tool-call output.

Uses the current google-genai SDK (google.genai).
"""
from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.models.gemini import (
    AddEventArgs,
    DeleteEventArgs,
    EditEventArgs,
    ToolCall,
)
from app.models.schedule import CalendarEvent, ScheduleRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini function declarations (google.genai style)
# ---------------------------------------------------------------------------

_ADD_EVENT_FUNC = types.FunctionDeclaration(
    name="add_event",
    description="Add a new event to the user's Google Calendar primary calendar.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(type=types.Type.STRING, description="Event title"),
            "start_time": types.Schema(
                type=types.Type.STRING,
                description="ISO 8601 datetime, e.g. 2026-04-25T09:00:00-07:00",
            ),
            "end_time": types.Schema(
                type=types.Type.STRING,
                description="ISO 8601 datetime, e.g. 2026-04-25T10:00:00-07:00",
            ),
            "location": types.Schema(
                type=types.Type.STRING, description="Optional event location"
            ),
        },
        required=["title", "start_time", "end_time"],
    ),
)

_EDIT_EVENT_FUNC = types.FunctionDeclaration(
    name="edit_event",
    description="Modify an existing event on the user's Google Calendar primary calendar.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "event_id": types.Schema(
                type=types.Type.STRING,
                description="Google Calendar event ID of the event to edit",
            ),
            "title": types.Schema(type=types.Type.STRING, description="New event title"),
            "start_time": types.Schema(
                type=types.Type.STRING,
                description="New start time as ISO 8601 datetime string",
            ),
            "end_time": types.Schema(
                type=types.Type.STRING,
                description="New end time as ISO 8601 datetime string",
            ),
            "location": types.Schema(
                type=types.Type.STRING, description="New event location"
            ),
        },
        required=["event_id"],
    ),
)

_DELETE_EVENT_FUNC = types.FunctionDeclaration(
    name="delete_event",
    description="Delete an existing event from the user's Google Calendar primary calendar.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "event_id": types.Schema(
                type=types.Type.STRING,
                description="Google Calendar event ID of the event to delete",
            ),
        },
        required=["event_id"],
    ),
)

_TOOLS = [types.Tool(function_declarations=[_ADD_EVENT_FUNC, _EDIT_EVENT_FUNC, _DELETE_EVENT_FUNC])]

# Force Gemini to always respond with a function call (no free text)
_TOOL_CONFIG = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(mode="ANY")
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _format_event(event: CalendarEvent) -> str:
    id_str = f" [event_id={event.event_id}]" if event.event_id else " [new, no id yet]"
    return f"- {event.title}{id_str}: {event.start} → {event.end}"


def _build_system_prompt(
    request: ScheduleRequest, current_gcal_events: list[CalendarEvent]
) -> str:
    prefs = request.preferences

    blocked_str = (
        ", ".join(f"{tr.start}–{tr.end}" for tr in prefs.no_work_time)
        if prefs.no_work_time
        else "none"
    )
    gcal_str = (
        "\n".join(_format_event(e) for e in current_gcal_events)
        if current_gcal_events
        else "  (no events currently on the calendar for this day)"
    )
    submitted_events_str = (
        "\n".join(_format_event(e) for e in request.events)
        if request.events
        else "  (none)"
    )

    tasks_parts = []
    for task in request.tasks:
        parts = [f"- {task.title}"]
        if task.duration_minutes:
            parts.append(f"({task.duration_minutes} min)")
        if task.deadline:
            parts.append(f"deadline={task.deadline}")
        tasks_parts.append(" ".join(parts))
    tasks_str = "\n".join(tasks_parts) if tasks_parts else "  (none)"

    constraint_lines = []
    if prefs.break_time > 0:
        constraint_lines.append(
            f"- Leave at least {prefs.break_time} minutes of free buffer between every event and task."
        )
    if prefs.context_switch:
        constraint_lines.append(
            "- Avoid context switching: group related task blocks together and do not interleave different tasks."
        )
    if prefs.burnout > 0:
        constraint_lines.append(
            f"- Do not schedule any task for more than {prefs.burnout} consecutive minutes. Insert a break or a different task type after that threshold."
        )
    if prefs.no_work_time:
        constraint_lines.append(
            f"- Do NOT schedule anything during these blocked windows: {blocked_str}. "
            "These windows must remain completely free."
        )
    constraints_str = (
        "\n".join(constraint_lines) if constraint_lines else "- No special scheduling constraints."
    )

    return f"""You are FlowState, an intelligent calendar scheduling assistant.

Your job is to analyse the user's existing Google Calendar, their submitted events and tasks, \
and their scheduling preferences, then output the minimal set of Google Calendar changes needed \
to satisfy the user's intent.

## Target Date
{request.date}

## Current Google Calendar Events (already on the calendar)
{gcal_str}

## User-Submitted Events (time-bound, the user wants these on the calendar)
{submitted_events_str}

## User-Submitted Tasks (need to be placed into free slots)
{tasks_str}

## Scheduling Constraints
{constraints_str}

## Instructions
1. Compare the submitted events against the current calendar:
   - If a submitted event has an event_id and differs from what's on the calendar, call edit_event.
   - If a submitted event has no event_id (or it doesn't exist on the calendar yet), call add_event.
   - If a calendar event is NOT in the submitted events list and is not a recurring event, call delete_event.
2. For each submitted task, find a suitable free slot respecting all constraints, then call add_event.
3. Respect all scheduling constraints strictly.
4. Output ONLY function calls — no plain text, no commentary.
5. All times must be ISO 8601 with a timezone offset (e.g., 2026-04-25T09:00:00-07:00).
"""


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------

async def call_gemini(
    request: ScheduleRequest,
    current_gcal_events: list[CalendarEvent],
) -> list[ToolCall]:
    """
    Call Gemini 2.5 Pro with the schedule request and current calendar state.

    Returns a list of ToolCall objects parsed from Gemini's function-call response.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    system_prompt = _build_system_prompt(request, current_gcal_events)
    user_message = (
        f"Please process my schedule for {request.date} and apply all necessary "
        "Google Calendar changes now."
    )

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=_TOOLS,
            tool_config=_TOOL_CONFIG,
        ),
    )

    tool_calls: list[ToolCall] = []

    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call is None:
                continue
            fn = part.function_call
            fn_name: str = fn.name
            args_dict: dict[str, Any] = dict(fn.args) if fn.args else {}

            try:
                if fn_name == "add_event":
                    args = AddEventArgs(**args_dict)
                elif fn_name == "edit_event":
                    args = EditEventArgs(**args_dict)
                elif fn_name == "delete_event":
                    args = DeleteEventArgs(**args_dict)
                else:
                    logger.warning("Unknown function call from Gemini: %s", fn_name)
                    continue

                tool_calls.append(ToolCall(function_name=fn_name, args=args))

            except Exception as exc:
                logger.error(
                    "Failed to parse Gemini function call '%s' with args %s: %s",
                    fn_name,
                    args_dict,
                    exc,
                )

    return tool_calls
