# flowstate-ai API Schemas

This document defines the exact JSON payloads the frontend needs to send and expect from the backend API endpoints. All models are strictly validated using Pydantic.

---

## 1. Preferences (`/preferences`)

### `UserPreferences` (PUT Request Body & GET Response Body)
Used to fetch and update the user's scheduling constraints.

```json
{
  "break_time": 15,
  "context_switch": true,
  "burnout": 90,
  "no_work_time": [
    {
      "start": "22:00",
      "end": "08:00"
    }
  ]
}
```

**Field Details:**
- `break_time` (integer, required): Minimum free minutes to leave between consecutive events/tasks. Must be >= 0.
- `context_switch` (boolean, required): Whether to avoid context switching by grouping task blocks together.
- `burnout` (integer, required): Maximum time in minutes that a task should be scheduled for consecutively. Must be >= 0.
- `no_work_time` (array of `TimeRange`, default `[]`): Time windows that must remain free (no events or tasks scheduled).

### `TimeRange`
```json
{
  "start": "09:00",
  "end": "10:00"
}
```
**Field Details:**
- `start` (string, required): Start time in `HH:MM` (24-hour format).
- `end` (string, required): End time in `HH:MM` (24-hour format).

---

## 2. Schedule Processing (`/schedule/process`)

### `ScheduleRequest` (POST Request Body)
The core payload sent when the user hits "submit" to optimize their day.

```json
{
  "date": "2026-04-25",
  "events": [
    {
      "event_id": "google_event_123xyz",
      "title": "Team Standup",
      "start": "2026-04-25T09:00:00",
      "end": "2026-04-25T10:00:00",
      "location": "Zoom",
      "is_all_day": false
    }
  ],
  "tasks": [
    {
      "task_id": "local_task_999",
      "title": "Write API documentation",
      "duration_minutes": 60,
      "deadline": "2026-04-25T17:00:00"
    }
  ],
  "preferences": {
    "break_time": 15,
    "context_switch": true,
    "burnout": 90,
    "no_work_time": []
  }
}
```

**Field Details:**
- `date` (string, required): Target date in `YYYY-MM-DD` format.
- `events` (array of `CalendarEvent`, default `[]`): Existing time-bound calendar events for the day (fetched earlier from `/calendar/events`) or new rigid events the user manually added on the frontend.
- `tasks` (array of `CalendarTask`, default `[]`): The floating work tasks that Gemini needs to schedule into the free slots.
- `preferences` (object `UserPreferences`, required): The user's preferences for this specific scheduling run.

#### `CalendarEvent`
- `event_id` (string | null, default `null`): Google Calendar event ID. Set to `null` if this is a brand new event the user just created on the frontend that isn't on GCal yet.
- `title` (string, required): Title of the event.
- `start` (string, required): ISO 8601 datetime string (e.g., `"2026-04-25T09:00:00"`).
- `end` (string, required): ISO 8601 datetime string.
- `location` (string | null, default `null`): Event location.
- `is_all_day` (boolean, default `false`): Whether it is an all-day event.

#### `CalendarTask`
- `task_id` (string | null, default `null`): The frontend's internal ID for this task (so the frontend can track it). Not a GCal ID.
- `title` (string, required): Title of the task.
- `duration_minutes` (integer | null, default `null`): Expected duration. Must be > 0. Gemini uses this to find a suitable free slot.
- `deadline` (string | null, default `null`): ISO 8601 datetime — a hard deadline for when this task must be finished.

### `ProcessResult` (POST Response Body)
Returned after Gemini successfully executes API calls to Google Calendar.

```json
{
  "date": "2026-04-25",
  "changes": [
    {
      "action": "added",
      "event_title": "Write API documentation",
      "event_id": "new_google_event_abc789",
      "error": null
    }
  ],
  "gemini_reasoning": null
}
```

**Field Details:**
- `date` (string): The date that was processed.
- `changes` (array of `ChangeResult`): A list summarizing every modification Gemini made directly to the user's Google Calendar.
- `gemini_reasoning` (string | null): Optional explanation from the AI about why it scheduled things the way it did (if implemented).

#### `ChangeResult`
- `action` (string): Will be exactly `"added"`, `"edited"`, or `"deleted"`.
- `event_title` (string): The title of the event that was modified.
- `event_id` (string | null): The Google Calendar event ID (especially useful for newly `"added"` events).
- `error` (string | null): If the Google Calendar API call failed for this specific event, the error message will be here.
