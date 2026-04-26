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
  "timezone": "America/Los_Angeles",
  "todos": [
    "Team Standup from 9 to 10am on Zoom",
    "Write API documentation (takes about an hour, due by 5pm)"
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
- `timezone` (string, required): User's local IANA timezone.
- `todos` (array of string, default `[]`): The floating work tasks and events in natural language that Gemini needs to schedule into the free slots. (e.g. "Meeting with Bob at 2pm", "Workout for 45 mins"). Gemini can also add invitees if email addresses are included in the natural language text.
- `preferences` (object `UserPreferences`, required): The user's preferences for this specific scheduling run.

### `ProcessResult` (POST Response Body)
Returned after Gemini successfully executes API calls to Google Calendar.

```json
{
  "message": "I scheduled your Team Standup from 9:00 AM to 10:00 AM. I held off on scheduling 'Dinner' as no start time was provided. For 'Write API documentation', I assumed a 1 hour duration. Please include specific times if you want a more exact schedule."
}
```

**Field Details:**
- `message` (string): A natural language message summarizing what was scheduled, what assumptions were made, what items were held off due to missing information, and a call-to-action for the user.
