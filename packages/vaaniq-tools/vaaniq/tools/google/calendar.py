"""Google Calendar tools.

Tools:
    google_calendar_list_events   — list upcoming events
    google_calendar_create_event  — create a new event
"""
import asyncio
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build

from vaaniq.tools.base import BaseTool
from vaaniq.tools.google.auth import build_google_credentials


def _build_service(org_keys: dict):
    creds = build_google_credentials(org_keys)
    return build("calendar", "v3", credentials=creds)


class GoogleCalendarListEvents(BaseTool):
    name = "google_calendar_list_events"
    description = "List upcoming events from Google Calendar."
    required_integration = "google"
    input_schema = {
        "type": "object",
        "properties": {
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID to query. Defaults to 'primary'.",
                "default": "primary",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (1–50).",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
            "days_ahead": {
                "type": "integer",
                "description": "How many days into the future to look.",
                "default": 7,
                "minimum": 1,
                "maximum": 90,
            },
        },
    }

    async def run(self, input: dict, org_keys: dict) -> dict:
        calendar_id = input.get("calendar_id", "primary")
        max_results = int(input.get("max_results", 10))
        days_ahead = int(input.get("days_ahead", 7))

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        def _fetch():
            service = _build_service(org_keys)
            result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return result.get("items", [])

        items = await asyncio.to_thread(_fetch)

        events = []
        for item in items:
            start = item.get("start", {})
            events.append({
                "id": item.get("id"),
                "title": item.get("summary", "(No title)"),
                "start": start.get("dateTime") or start.get("date"),
                "end": (item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")),
                "location": item.get("location"),
                "description": item.get("description"),
                "attendees": [
                    a.get("email") for a in item.get("attendees", [])
                ],
                "link": item.get("htmlLink"),
            })

        return {"events": events, "count": len(events)}


class GoogleCalendarCreateEvent(BaseTool):
    name = "google_calendar_create_event"
    description = "Create a new event in Google Calendar."
    required_integration = "google"
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title / summary.",
            },
            "start_time": {
                "type": "string",
                "format": "date-time",
                "description": "Start datetime in ISO 8601 format, e.g. '2026-04-10T14:00:00+05:30'.",
            },
            "end_time": {
                "type": "string",
                "format": "date-time",
                "description": "End datetime in ISO 8601 format. Must be after start_time.",
            },
            "description": {
                "type": "string",
                "description": "Optional event description / notes.",
            },
            "location": {
                "type": "string",
                "description": "Optional location string.",
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses (e.g. 'john@example.com'). Must be valid email addresses — do NOT pass names. If you only have a name, ask the user for their email first.",
            },
            "timezone": {
                "type": "string",
                "description": (
                    "IANA timezone name for the event, e.g. 'Asia/Kolkata', 'America/New_York', 'UTC'. "
                    "Used to localise datetimes that have no timezone offset. Defaults to 'UTC'."
                ),
                "default": "UTC",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID. Defaults to 'primary'.",
                "default": "primary",
            },
            "reminder_minutes": {
                "type": "integer",
                "description": "Send an email reminder this many minutes before the event. Defaults to 30.",
                "default": 30,
            },
        },
        "required": ["title", "start_time"],
    }

    def normalize_input(self, inputs: dict) -> dict:
        inputs = super().normalize_input(inputs)  # type coercion (reminder_minutes str→int, etc.)
        start_raw = inputs.get("start_time")
        end_raw = inputs.get("end_time") or None  # treat empty string as missing

        if start_raw:
            from datetime import datetime as dt, timedelta
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            tz_name = inputs.get("timezone") or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except (ZoneInfoNotFoundError, KeyError):
                raise ValueError(
                    f"Unknown timezone '{tz_name}'. Use an IANA timezone name like 'Asia/Kolkata' or 'UTC'."
                )

            def _parse_and_localize(raw: str, field: str) -> dt:
                try:
                    parsed = dt.fromisoformat(raw)
                except ValueError:
                    raise ValueError(
                        f"{field} '{raw}' is not a valid ISO 8601 datetime. "
                        f"Expected format: '2026-04-10T14:00' or '2026-04-10T14:00:00+05:30'."
                    )
                # If naive (no timezone info), localize using the provided timezone
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=tz)
                return parsed

            start = _parse_and_localize(start_raw, "start_time")
            # Write back the timezone-aware ISO string so the API receives it correctly
            inputs["start_time"] = start.isoformat()

            if not end_raw:
                inputs["end_time"] = (start + timedelta(hours=1)).isoformat()
            else:
                end = _parse_and_localize(end_raw, "end_time")
                if end <= start:
                    raise ValueError(
                        f"end_time ({end_raw}) must be after start_time ({start_raw}). "
                        "The meeting end time cannot be before or equal to the start time."
                    )
                inputs["end_time"] = end.isoformat()

        return inputs

    async def run(self, input: dict, org_keys: dict) -> dict:
        calendar_id = input.get("calendar_id", "primary")
        reminder_minutes = int(input.get("reminder_minutes", 30))

        event_body: dict = {
            "summary": input["title"],
            "start": {"dateTime": input["start_time"]},
            "end": {"dateTime": input["end_time"]},
            # Always set an email reminder so the organiser receives a notification
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": reminder_minutes},
                    {"method": "popup", "minutes": 10},
                ],
            },
        }
        if input.get("description"):
            event_body["description"] = input["description"]
        if input.get("location"):
            event_body["location"] = input["location"]
        if input.get("attendees"):
            event_body["attendees"] = [{"email": e} for e in input["attendees"]]

        def _create():
            service = _build_service(org_keys)
            return service.events().insert(
                calendarId=calendar_id,
                body=event_body,
                sendUpdates="all" if input.get("attendees") else "none",
            ).execute()

        created = await asyncio.to_thread(_create)

        return {
            "event_id": created.get("id"),
            "title": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
            "link": created.get("htmlLink"),
            "status": created.get("status"),
        }
