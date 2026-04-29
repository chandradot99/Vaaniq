"""TOOL_REGISTRY — maps tool name strings to BaseTool instances.

Add new tools here after implementing them in their module.
The registry is imported by:
  - naaviq-graph RunToolNode   (executes a specific tool by name)
  - naaviq-server tools router (exposes tool catalog to the frontend)
"""
from naaviq.tools.base import BaseTool
from naaviq.tools.google.calendar import GoogleCalendarCreateEvent, GoogleCalendarListEvents
from naaviq.tools.google.gmail import GmailSendEmail
from naaviq.tools.google.sheets import GoogleSheetsAppendRow, GoogleSheetsReadRange

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
