"""Schedule router — core endpoint that processes the user's submit payload."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbDep
from app.models.ai import AddEventArgs, DeleteEventArgs, EditEventArgs, FinalizeScheduleArgs
from app.models.response import ProcessResult
from app.models.schedule import ScheduleRequest
from app.services import auth_service, calendar_service, ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post(
    "/process",
    response_model=ProcessResult,
    summary="Process todo list and apply Google Calendar changes",
)
async def process_schedule(
    request: ScheduleRequest,
    current_user: CurrentUser,
    db: DbDep,
):
    """
    Core endpoint — the full AI scheduling pipeline:

    1. Fetch the user's current primary calendar events for the given date.
    2. Send date, todos, and preferences to the AI model.
    3. Parse the AI's function-call response (add_event / edit_event / delete_event / finalize_schedule).
    4. Execute each tool call against the Google Calendar API.
    5. Return a ProcessResult containing the summary message.
    """
    logger.info("Processing schedule request for date %s with %d todos", request.date, len(request.todos))
    
    # --- Step 1: Load credentials ---
    credentials = await auth_service.get_credentials(current_user["user_id"], db)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No stored credentials. Please log in again.",
        )

    # --- Step 2: Fetch current calendar state ---
    try:
        current_events = await calendar_service.get_events_for_date(
            credentials, request.date, request.timezone
        )
    except Exception as exc:
        logger.error("Failed to fetch calendar events: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch Google Calendar events: {exc}",
        )

    # --- Step 3: Call AI Model ---
    try:
        tool_calls = await ai_service.call_ai(request, current_events)
    except Exception as exc:
        logger.error("AI call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI API error: {exc}",
        )

    # --- Step 4: Execute each tool call ---
    logger.info("AI returned %d tool calls", len(tool_calls))
    message = "No summary provided by the AI."

    for tool_call in tool_calls:
        fn = tool_call.function_name
        args = tool_call.args
        
        logger.info("Executing tool: %s with args: %s", fn, args.model_dump())

        try:
            if fn == "finalize_schedule" and isinstance(args, FinalizeScheduleArgs):
                message = args.message

            elif fn == "add_event" and isinstance(args, AddEventArgs):
                await calendar_service.add_event(credentials, args, request.timezone)

            elif fn == "edit_event" and isinstance(args, EditEventArgs):
                await calendar_service.edit_event(credentials, args.event_id, args, request.timezone)

            elif fn == "delete_event" and isinstance(args, DeleteEventArgs):
                await calendar_service.delete_event(credentials, args.event_id)

        except Exception as exc:
            logger.error("Failed to execute %s with args %s: %s", fn, args.model_dump(), exc)

    return ProcessResult(message=message)
