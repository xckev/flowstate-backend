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
    FinalizeScheduleArgs,
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
            "is_all_day": types.Schema(
                type=types.Type.BOOLEAN,
                description="True if this is an all-day event with no specific start/end time",
            ),
            "start_time": types.Schema(
                type=types.Type.STRING,
                description="Timed events: ISO 8601 with timezone offset, e.g. 2026-04-25T09:00:00-07:00. All-day events: date string, e.g. 2026-04-25",
            ),
            "end_time": types.Schema(
                type=types.Type.STRING,
                description="Timed events: ISO 8601 with timezone offset. All-day events: exclusive end date (typically start + 1 day), e.g. 2026-04-26",
            ),
            "location": types.Schema(
                type=types.Type.STRING, description="Optional event location"
            ),
            "attendees": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Optional list of email addresses to invite",
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
            "is_all_day": types.Schema(
                type=types.Type.BOOLEAN,
                description="True if converting to or editing an all-day event",
            ),
            "start_time": types.Schema(
                type=types.Type.STRING,
                description="Timed events: ISO 8601 with timezone offset. All-day events: date string (YYYY-MM-DD)",
            ),
            "end_time": types.Schema(
                type=types.Type.STRING,
                description="Timed events: ISO 8601 with timezone offset. All-day events: exclusive end date (YYYY-MM-DD)",
            ),
            "location": types.Schema(
                type=types.Type.STRING, description="New event location"
            ),
            "attendees": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Optional list of email addresses to invite",
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

_FINALIZE_FUNC = types.FunctionDeclaration(
    name="finalize_schedule",
    description="Finalize the scheduling process and provide the summary message to the user.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "message": types.Schema(
                type=types.Type.STRING,
                description="Summary of scheduled items, held off items, assumptions made, and a call-to-action.",
            ),
        },
        required=["message"],
    ),
)

_TOOLS = [types.Tool(function_declarations=[_ADD_EVENT_FUNC, _EDIT_EVENT_FUNC, _DELETE_EVENT_FUNC, _FINALIZE_FUNC])]

# Force Gemini to always respond with a function call (no free text)
_TOOL_CONFIG = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(mode="ANY")
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _format_event(event: CalendarEvent) -> str:
    id_str = f" [event_id={event.event_id}]" if event.event_id else " [new, no id yet]"
    if event.is_all_day:
        return f"- {event.title}{id_str}: {event.start[:10]} (all-day)"
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
    todos_str = (
        "\n".join(f"- {todo}" for todo in request.todos)
        if request.todos
        else "  (no todos provided)"
    )

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

Your job is to analyse the user's existing Google Calendar, their submitted natural language todos, \
and their scheduling preferences, then output the minimal set of Google Calendar changes needed \
to satisfy the user's intent.

## Target Date
{request.date}

## Current Google Calendar Events (already on the calendar)
{gcal_str}

## User Todos
{todos_str}

## Scheduling Constraints
{constraints_str}

## Instructions
1. Interpret the natural language "todos" into events and/or tasks to be scheduled on the user's Google Calendar.
2. **If there are no "todos" provided, you must clear the day by calling `delete_event` for every single event currently on the calendar.**
3. Use your best judgement to determine if a todo matches an existing event on the calendar. If it matches AND the calendar data is already correct, you should do NOTHING for that event. If it matches but needs updating (e.g. time change), call `edit_event`.
4. If an item is new, call add_event to place it into a suitable free slot.
5. **If a calendar event currently on the calendar is NOT represented in the user's "todos" list, you MUST call `delete_event` to remove it.** The "todos" list is the absolute source of truth for the day.
6. **Hold off** on scheduling an event if its start time is unknown or ambiguous.
7. If the end time (for an event) or estimated duration (for a task) is not provided, **default to assuming 1 hour** for all unspecified calendar entries.
8. You can invite attendees by including their email addresses in the `attendees` field of `add_event` or `edit_event`.
9. You MUST call `finalize_schedule` exactly once. Provide a `message` that summarizes:
   - What things you have scheduled.
   - What things you decided to hold off on scheduling due to lack of information.
   - What assumptions you made (e.g., assuming 1 hour for unspecified entries).
   - If there were no todos, confirm that you have cleared the day.
   - If you made any assumptions or held off on anything, end the message with a call-to-action indicating what the user should include in their todos if they want the calendar to be more exact.
9. Output ONLY function calls — no plain text, no commentary. Use `finalize_schedule` for the textual response.
10. For timed events: all times must be ISO 8601 with a timezone offset (e.g., 2026-04-25T09:00:00-07:00).
11. For all-day events: set is_all_day=true, use the exact date shown (YYYY-MM-DD) for start_time, and set end_time to the following day (e.g., start 2026-04-25 → end 2026-04-26). Never assign a time to an all-day event.
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
                elif fn_name == "finalize_schedule":
                    args = FinalizeScheduleArgs(**args_dict)
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
