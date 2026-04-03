"""TOOL_REGISTRY — maps tool name strings to BaseTool instances.

Add new tools here after implementing them in their module.
The registry is imported by:
  - vaaniq-graph RunToolNode   (executes a specific tool by name)
  - vaaniq-server tools router (exposes tool catalog to the frontend)
"""
from vaaniq.tools.base import BaseTool
from vaaniq.tools.google.calendar import GoogleCalendarListEvents, GoogleCalendarCreateEvent
from vaaniq.tools.google.gmail import GmailSendEmail
from vaaniq.tools.google.sheets import GoogleSheetsReadRange, GoogleSheetsAppendRow

TOOL_REGISTRY: dict[str, BaseTool] = {
    # Google Calendar
    "google_calendar_list_events": GoogleCalendarListEvents(),
    "google_calendar_create_event": GoogleCalendarCreateEvent(),
    # Gmail
    "gmail_send_email": GmailSendEmail(),
    # Google Sheets
    "google_sheets_read_range": GoogleSheetsReadRange(),
    "google_sheets_append_row": GoogleSheetsAppendRow(),
}
