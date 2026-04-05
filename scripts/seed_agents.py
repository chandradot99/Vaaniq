"""
Seed the Smart Assistant test agent.

This agent tests every major feature built so far:
  - Multi-turn conversation loop (inbound_message)
  - ReAct tool calling (llm_response with google_calendar_list_events)
  - Condition-based routing
  - Structured data collection (collect_data)
  - Human-in-the-loop approval (human_review)
  - Explicit tool execution (run_tool)
  - Goto edges (loop-back without visual lines)
  - Node groups / swimlanes

Usage:
    uv run python scripts/seed_agents.py --org-id <org_id>

The org_id can be found in the database or from the JWT token after logging in.
"""

import argparse
import asyncio
import uuid

from vaaniq.server.core.database import async_session_factory
import vaaniq.server.auth.models  # noqa: F401  — ensures FK tables are loaded
from vaaniq.server.agents.models import Agent

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

AGENTS = [
    # ------------------------------------------------------------------
    # Calendar Assistant (ReAct) — single LLM node, LLM decides everything
    # ------------------------------------------------------------------
    {
        "name": "Calendar Assistant",
        "language": "en",
        "simple_mode": False,
        "system_prompt": (
            "You are a helpful assistant that manages Google Calendar. "
            "Use your tools to check and create events. "
            "Ask clarifying questions naturally when you need more information."
        ),
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "groups": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "label": "Greet",
                    "position": {"x": 80, "y": 200},
                    "config": {
                        "instructions": (
                            "Greet the user and let them know you can help them check "
                            "or create Google Calendar events. Ask how you can help."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "wait",
                    "type": "inbound_message",
                    "label": "Wait",
                    "position": {"x": 280, "y": 200},
                    "config": {},
                },
                {
                    "id": "agent",
                    "type": "llm_response",
                    "label": "Agent",
                    "position": {"x": 480, "y": 200},
                    "config": {
                        "instructions": (
                            "Help the user manage their Google Calendar.\n\n"
                            "- To check events: call google_calendar_list_events\n"
                            "- To create an event: ask the user for the name, date, and time "
                            "if not already provided, then call google_calendar_create_event\n"
                            "- Answer follow-up questions conversationally\n\n"
                            "When the user says goodbye or there's nothing more to do, "
                            "say a warm farewell."
                        ),
                        "rag_enabled": False,
                        "tools": [
                            "google_calendar_list_events",
                            "google_calendar_create_event",
                        ],
                    },
                },
                {
                    "id": "route",
                    "type": "condition",
                    "label": "Done?",
                    "position": {"x": 680, "y": 200},
                    "config": {
                        "router_prompt": (
                            "Did the agent just say goodbye or indicate the conversation is over?\n"
                            "- done: agent said farewell / session is ending\n"
                            "- continue: conversation is still going"
                        ),
                        "routes": [
                            {"label": "done",     "description": "Agent said goodbye"},
                            {"label": "continue", "description": "Conversation still going"},
                        ],
                    },
                },
                {
                    "id": "next_turn",
                    "type": "inbound_message",
                    "label": "Next Turn",
                    "position": {"x": 880, "y": 160},
                    "config": {},
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "label": "End",
                    "position": {"x": 880, "y": 260},
                    "config": {
                        "farewell_message": "Goodbye! Have a great day!",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet",     "target": "wait"},
                {"id": "e2", "source": "wait",      "target": "agent"},
                {"id": "e3", "source": "agent",     "target": "route"},
                {"id": "e4", "source": "route",     "target": "next_turn", "condition": "continue"},
                {"id": "e5", "source": "route",     "target": "end",       "condition": "done"},
                {"id": "e6", "source": "next_turn", "target": "agent",     "goto": True},
            ],
        },
    },

    # ------------------------------------------------------------------
    # Personal Google Assistant — tests Calendar + Gmail + Sheets tools
    # via condition routing, collect_data, and goto loops.
    #
    # Before running: replace REPLACE_WITH_YOUR_SPREADSHEET_ID in the
    # do_booking node's instructions with a real Google Sheets ID.
    # The sheet should have headers: Name | Email | Meeting | DateTime | Status
    # ------------------------------------------------------------------
    {
        "name": "Personal Google Assistant",
        "language": "en",
        "simple_mode": False,
        "system_prompt": (
            "You are a helpful personal assistant connected to Google. "
            "You can book meetings, check schedules, and send emails."
        ),
        "graph_config": {
            "entry_point": "start",
            "guards": [],
            "groups": [],
            "nodes": [
                # ── Entry ──────────────────────────────────────────────
                {
                    "id": "start",
                    "type": "start",
                    "label": "Start",
                    "position": {"x": 80, "y": 300},
                    "config": {
                        "system_message": (
                            "You are a helpful personal assistant connected to Google. "
                            "You help users book meetings on Google Calendar, check their "
                            "upcoming schedule, and send emails via Gmail. "
                            "Always be concise and friendly."
                        ),
                        "greeting": (
                            "Hi! I'm your personal Google assistant. I can help you with:\n"
                            "• Book a meeting — create a calendar event, send an invite, and log it to Sheets\n"
                            "• Check your schedule — see what's coming up this week\n"
                            "• Send an email — quick emails straight from Gmail\n\n"
                            "What would you like to do?"
                        ),
                    },
                },
                {
                    "id": "wait",
                    "type": "inbound_message",
                    "label": "Wait",
                    "position": {"x": 280, "y": 300},
                    "config": {},
                },
                {
                    "id": "route",
                    "type": "condition",
                    "label": "Route Intent",
                    "position": {"x": 500, "y": 300},
                    "config": {
                        "router_prompt": "Based on the user's latest message, what do they want to do?",
                        "routes": [
                            {
                                "label": "book_meeting",
                                "description": "User wants to schedule, book, or create a meeting or calendar event",
                            },
                            {
                                "label": "check_schedule",
                                "description": "User wants to see upcoming calendar events or check their schedule",
                            },
                            {
                                "label": "send_email",
                                "description": "User wants to send an email to someone",
                            },
                            {
                                "label": "end",
                                "description": "User says goodbye, thanks, or has nothing else to do",
                            },
                        ],
                    },
                },

                # ── Book meeting branch ────────────────────────────────
                # collect_data gathers all required fields. Start and end
                # datetime are asked in ISO format (YYYY-MM-DDTHH:MM) so
                # run_tool can append the timezone directly without an LLM.
                {
                    "id": "collect_booking",
                    "type": "collect_data",
                    "label": "Collect Booking",
                    "position": {"x": 750, "y": 80},
                    "config": {
                        "instructions": (
                            "The user wants to book a calendar meeting. They may mention the title, "
                            "attendee name, date, or time upfront — extract whatever they already provided "
                            "so we can skip asking for it. "
                            "Dates and times may be informal (e.g. 'tomorrow 10pm', 'next Monday 3-4pm'). "
                            "Datetimes should be in YYYY-MM-DDTHH:MM format."
                        ),
                        "fields": [
                            {
                                "name": "meeting_title",
                                "type": "string",
                                "prompt": "What is the meeting about? (event title)",
                                "required": True,
                            },
                            {
                                "name": "attendee_name",
                                "type": "string",
                                "prompt": "Who are you meeting with? (their name)",
                                "required": True,
                            },
                            {
                                "name": "attendee_email",
                                "type": "string",
                                "prompt": "What is their email address?",
                                "required": True,
                            },
                            {
                                "name": "start_datetime",
                                "type": "string",
                                "prompt": "Start date and time? (format: YYYY-MM-DDTHH:MM e.g. 2026-04-10T14:00)",
                                "required": True,
                            },
                            {
                                "name": "end_datetime",
                                "type": "string",
                                "prompt": "End date and time? (format: YYYY-MM-DDTHH:MM e.g. 2026-04-10T15:00, or press Enter to default to 1 hour after start)",
                                "required": False,
                            },
                        ],
                    },
                },
                # run_tool: creates the calendar event directly from collected fields.
                # timezone field localises naive datetimes from collect_data to IST.
                {
                    "id": "create_event",
                    "type": "run_tool",
                    "label": "Create Calendar Event",
                    "position": {"x": 1000, "y": 20},
                    "config": {
                        "tool": "google_calendar_create_event",
                        "input": {
                            "title":      "{{collected.meeting_title}}",
                            "start_time": "{{collected.start_datetime}}",
                            "end_time":   "{{collected.end_datetime}}",
                            "attendees":  ["{{collected.attendee_email}}"],
                            "timezone":   "Asia/Kolkata",
                        },
                    },
                },
                # run_tool: sends a confirmation email to the attendee.
                # The email body is a static template filled from collected fields.
                {
                    "id": "send_invite",
                    "type": "run_tool",
                    "label": "Send Invite Email",
                    "position": {"x": 1000, "y": 140},
                    "config": {
                        "tool": "gmail_send_email",
                        "input": {
                            "to":      "{{collected.attendee_email}}",
                            "subject": "Meeting Invite: {{collected.meeting_title}}",
                            "body": (
                                "Hi {{collected.attendee_name}},\n\n"
                                "You have been invited to a meeting.\n\n"
                                "Title: {{collected.meeting_title}}\n"
                                "Start: {{collected.start_datetime}}\n"
                                "End:   {{collected.end_datetime}}\n\n"
                                "A calendar invite has also been sent to your email.\n\n"
                                "See you then!"
                            ),
                        },
                    },
                },
                # run_tool: logs the booking row to Google Sheets.
                # Replace REPLACE_WITH_YOUR_SPREADSHEET_ID before running.
                {
                    "id": "log_booking",
                    "type": "run_tool",
                    "label": "Log to Sheets",
                    "position": {"x": 1000, "y": 260},
                    "config": {
                        "tool": "google_sheets_append_row",
                        "input": {
                            "spreadsheet_id": "REPLACE_WITH_YOUR_SPREADSHEET_ID",
                            "range":  "Sheet1",
                            "values": [
                                "{{collected.attendee_name}}",
                                "{{collected.attendee_email}}",
                                "{{collected.meeting_title}}",
                                "{{collected.start_datetime}}",
                                "scheduled",
                            ],
                        },
                    },
                },
                # llm_response: no tools — only generates the confirmation message.
                # The conversation history already contains all the booking details
                # from collect_data, so the LLM can reference them naturally.
                {
                    "id": "confirm_booking",
                    "type": "llm_response",
                    "label": "Confirm Booking",
                    "position": {"x": 1250, "y": 140},
                    "config": {
                        "instructions": (
                            "All three steps have just been completed automatically:\n"
                            "1. The calendar event has been created\n"
                            "2. A confirmation email has been sent to the attendee\n"
                            "3. The booking has been logged to Google Sheets\n\n"
                            "Write a short, friendly confirmation to the user. "
                            "Mention the meeting title and time (from the conversation). "
                            "Ask if there is anything else you can help with."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },

                # ── Check schedule branch ──────────────────────────────
                # run_tool: fetches calendar events and saves them to rag_context
                # so the llm_response node below can read and format them.
                {
                    "id": "list_events",
                    "type": "run_tool",
                    "label": "Fetch Calendar Events",
                    "position": {"x": 750, "y": 320},
                    "config": {
                        "tool": "google_calendar_list_events",
                        "input": {
                            "days_ahead":  7,
                            "max_results": 10,
                        },
                        "save_response_to": "rag_context",
                    },
                },
                # llm_response: reads the raw event data from rag_context and
                # formats it into a readable schedule for the user. No tools needed.
                {
                    "id": "show_schedule",
                    "type": "llm_response",
                    "label": "Show Schedule",
                    "position": {"x": 1000, "y": 320},
                    "config": {
                        "instructions": (
                            "The user's upcoming Google Calendar events have just been fetched "
                            "and are available in your context below. "
                            "Format them into a clean, readable list for the user — show each "
                            "event's title, date, and time. "
                            "If the calendar is empty, tell them so. "
                            "Then ask if there is anything else you can help with."
                        ),
                        "rag_enabled": True,
                        "tools": [],
                    },
                },

                # ── Send email branch ──────────────────────────────────
                {
                    "id": "collect_email",
                    "type": "collect_data",
                    "label": "Collect Email",
                    "position": {"x": 750, "y": 520},
                    "config": {
                        "fields": [
                            {
                                "name": "email_to",
                                "type": "string",
                                "prompt": "Who should I send it to? (email address)",
                                "required": True,
                            },
                            {
                                "name": "email_subject",
                                "type": "string",
                                "prompt": "What's the subject line?",
                                "required": True,
                            },
                            {
                                "name": "email_body",
                                "type": "string",
                                "prompt": "What should the email say?",
                                "required": True,
                            },
                        ],
                    },
                },
                # run_tool: sends the email directly from collected fields — no LLM needed.
                {
                    "id": "send_email",
                    "type": "run_tool",
                    "label": "Send Email",
                    "position": {"x": 1000, "y": 520},
                    "config": {
                        "tool": "gmail_send_email",
                        "input": {
                            "to":      "{{collected.email_to}}",
                            "subject": "{{collected.email_subject}}",
                            "body":    "{{collected.email_body}}",
                        },
                    },
                },
                # llm_response: no tools — only generates the sent confirmation.
                {
                    "id": "confirm_email",
                    "type": "llm_response",
                    "label": "Confirm Email Sent",
                    "position": {"x": 1250, "y": 520},
                    "config": {
                        "instructions": (
                            "The email has just been sent successfully. "
                            "Confirm to the user that it was sent — mention the recipient "
                            "and subject (from the conversation). "
                            "Ask if there is anything else you can help with."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },

                # ── Terminal ───────────────────────────────────────────
                {
                    "id": "farewell",
                    "type": "end_session",
                    "label": "Farewell",
                    "position": {"x": 750, "y": 720},
                    "config": {
                        "farewell_message": "Great talking with you! Have a wonderful day. Goodbye!",
                    },
                },
            ],
            "edges": [
                {"id": "e1",  "source": "start",           "target": "wait"},
                {"id": "e2",  "source": "wait",            "target": "route"},
                # Routing
                {"id": "e3",  "source": "route",           "target": "collect_booking", "condition": "book_meeting"},
                {"id": "e4",  "source": "route",           "target": "list_events",     "condition": "check_schedule"},
                {"id": "e5",  "source": "route",           "target": "collect_email",   "condition": "send_email"},
                {"id": "e6",  "source": "route",           "target": "farewell",        "condition": "end"},
                # Book meeting flow: collect → create event → send invite → log → confirm → loop
                {"id": "e7",  "source": "collect_booking", "target": "create_event"},
                {"id": "e8",  "source": "create_event",    "target": "send_invite"},
                {"id": "e9",  "source": "send_invite",     "target": "log_booking"},
                {"id": "e10", "source": "log_booking",     "target": "confirm_booking"},
                {"id": "e11", "source": "confirm_booking", "target": "wait",
                 "goto": True, "goto_node_position": {"x": 1450, "y": 140}},
                # Check schedule flow: fetch → format → loop
                {"id": "e12", "source": "list_events",     "target": "show_schedule"},
                {"id": "e13", "source": "show_schedule",   "target": "wait",
                 "goto": True, "goto_node_position": {"x": 1180, "y": 320}},
                # Send email flow: collect → send → confirm → loop
                {"id": "e14", "source": "collect_email",   "target": "send_email"},
                {"id": "e15", "source": "send_email",      "target": "confirm_email"},
                {"id": "e16", "source": "confirm_email",   "target": "wait",
                 "goto": True, "goto_node_position": {"x": 1450, "y": 520}},
            ],
        },
    },

    # ------------------------------------------------------------------
    # Smart Assistant — tests all node types + groups + goto edges
    # ------------------------------------------------------------------
    {
        "name": "Smart Assistant",
        "language": "en",
        "simple_mode": False,
        "system_prompt": (
            "You are a friendly assistant that helps users manage their Google Calendar. "
            "You can check upcoming events and create new ones."
        ),
        "graph_config": {
            "entry_point": "greet",
            "guards": [],

            # ── Groups (swimlanes) ─────────────────────────────────────
            "groups": [
                {
                    "id": "group_conversation",
                    "label": "Conversation Loop",
                    "color_index": 1,          # Blue
                    "position": {"x": 40, "y": 40},
                    "width": 780,
                    "height": 220,
                },
                {
                    "id": "group_create_event",
                    "label": "Create Event Flow",
                    "color_index": 3,          # Green
                    "position": {"x": 40, "y": 340},
                    "width": 1040,
                    "height": 220,
                },
            ],

            # ── Nodes ──────────────────────────────────────────────────
            "nodes": [
                # ── Conversation Loop ──────────────────────────────────
                {
                    "id": "greet",
                    "type": "llm_response",
                    "label": "Greet",
                    "parent_id": "group_conversation",
                    "position": {"x": 40, "y": 100},   # relative to group
                    "config": {
                        "instructions": (
                            "Greet the user warmly and let them know you can help them "
                            "manage their Google Calendar — checking upcoming events or "
                            "creating new ones. Ask how you can help."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "wait",
                    "type": "inbound_message",
                    "label": "Wait",
                    "parent_id": "group_conversation",
                    "position": {"x": 220, "y": 100},  # relative to group
                    "config": {},
                },
                {
                    "id": "agent",
                    "type": "llm_response",
                    "label": "Agent",
                    "parent_id": "group_conversation",
                    "position": {"x": 400, "y": 100},  # relative to group
                    "config": {
                        "instructions": (
                            "You are a helpful assistant that manages Google Calendar.\n\n"
                            "You can:\n"
                            "- Check the user's upcoming calendar events using the list_events tool\n"
                            "- Help the user create a new event when requested\n"
                            "- Answer general questions conversationally\n\n"
                            "When the user wants to check their calendar, call google_calendar_list_events "
                            "and summarise the results in a friendly way.\n"
                            "When the user says goodbye or is done, say farewell."
                        ),
                        "rag_enabled": False,
                        "tools": ["google_calendar_list_events"],
                    },
                },
                # next_turn waits for the user's next message then loops back to agent.
                {
                    "id": "next_turn",
                    "type": "inbound_message",
                    "label": "Next Turn",
                    "parent_id": "group_conversation",
                    "position": {"x": 580, "y": 100},  # relative to group
                    "config": {},
                },

                # ── Routing — evaluated after the agent responds ───────
                {
                    "id": "route_intent",
                    "type": "condition",
                    "label": "Route Intent",
                    "position": {"x": 900, "y": 140},
                    "config": {
                        "router_prompt": (
                            "Based on the agent's last response and the conversation so far, "
                            "what should happen next?\n"
                            "- create_event: The user wants to create a new calendar event "
                            "and the agent has acknowledged this\n"
                            "- done: The user said goodbye or the session is naturally ending\n"
                            "- continue: The agent just responded and is waiting for the user's "
                            "next message (default for most turns)"
                        ),
                        "routes": [
                            {"label": "create_event", "description": "User wants to create a calendar event"},
                            {"label": "done",         "description": "Session is ending"},
                            {"label": "continue",     "description": "Continue — wait for next user message"},
                        ],
                    },
                },

                # ── Create Event Flow ──────────────────────────────────
                {
                    "id": "collect_event",
                    "type": "collect_data",
                    "label": "Collect Event Details",
                    "parent_id": "group_create_event",
                    "position": {"x": 40, "y": 100},   # relative to group
                    "config": {
                        "fields": [
                            {
                                "name": "event_name",
                                "type": "string",
                                "prompt": "What would you like to call this event?",
                                "required": True,
                            },
                            {
                                "name": "event_date",
                                "type": "date",
                                "prompt": "What date? (e.g. tomorrow, April 10th)",
                                "required": True,
                            },
                            {
                                "name": "event_time",
                                "type": "string",
                                "prompt": "What time? (e.g. 3pm, 14:30)",
                                "required": True,
                            },
                        ],
                    },
                },
                {
                    "id": "approve_event",
                    "type": "human_review",
                    "label": "Approve Event",
                    "parent_id": "group_create_event",
                    "position": {"x": 280, "y": 100},  # relative to group
                    "config": {
                        "message": "Create this calendar event?",
                        "context_variable": "event_name",
                    },
                },
                {
                    "id": "create_event",
                    "type": "run_tool",
                    "label": "Create Event",
                    "parent_id": "group_create_event",
                    "position": {"x": 520, "y": 60},   # relative to group — approve branch
                    "config": {
                        "tool": "google_calendar_create_event",
                        "input": {
                            "summary":    "{{collected.event_name}}",
                            "start_time": "{{collected.event_date}} {{collected.event_time}}",
                        },
                    },
                },
                {
                    "id": "confirm_event",
                    "type": "llm_response",
                    "label": "Confirm Event",
                    "parent_id": "group_create_event",
                    "position": {"x": 760, "y": 60},   # relative to group — after create
                    "config": {
                        "instructions": (
                            "Tell the user their calendar event was created successfully. "
                            "Mention the event name. Ask if there's anything else you can help with."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "event_cancelled",
                    "type": "llm_response",
                    "label": "Cancelled",
                    "parent_id": "group_create_event",
                    "position": {"x": 520, "y": 140},  # relative to group — reject branch
                    "config": {
                        "instructions": (
                            "Tell the user the event creation was cancelled. "
                            "Ask if there's anything else you can help with."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },

                # ── Terminal ───────────────────────────────────────────
                {
                    "id": "end",
                    "type": "end_session",
                    "label": "End",
                    "position": {"x": 1160, "y": 140},
                    "config": {
                        "farewell_message": "Goodbye! Have a great day!",
                    },
                },
            ],

            # ── Edges ──────────────────────────────────────────────────
            "edges": [
                # Greeting then wait for first user message
                {"id": "e1", "source": "greet",          "target": "wait"},
                {"id": "e2", "source": "wait",           "target": "agent"},

                # Agent responds, then route
                {"id": "e3", "source": "agent",          "target": "route_intent"},

                # Route intent
                {"id": "e4", "source": "route_intent",   "target": "next_turn",      "condition": "continue"},
                {"id": "e5", "source": "route_intent",   "target": "collect_event",  "condition": "create_event"},
                {"id": "e6", "source": "route_intent",   "target": "end",            "condition": "done"},

                # "continue" path — capture next user message then loop back to agent
                {"id": "e7", "source": "next_turn",      "target": "agent",          "goto": True},

                # Create event flow
                {"id": "e8",  "source": "collect_event",  "target": "approve_event"},
                {"id": "e9",  "source": "approve_event",  "target": "create_event",   "condition": "approve"},
                {"id": "e10", "source": "approve_event",  "target": "event_cancelled","condition": "reject"},

                # Confirm creation then return to conversation loop
                {"id": "e11", "source": "create_event",    "target": "confirm_event"},
                {"id": "e12", "source": "confirm_event",   "target": "next_turn",    "goto": True},
                {"id": "e13", "source": "event_cancelled", "target": "next_turn",    "goto": True},
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def seed(org_id: str) -> None:
    async with async_session_factory() as db:
        for agent_def in AGENTS:
            agent = Agent(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=agent_def["name"],
                language=agent_def["language"],
                simple_mode=agent_def["simple_mode"],
                system_prompt=agent_def["system_prompt"],
                graph_config=agent_def["graph_config"],
            )
            db.add(agent)
            print(f"  + {agent.name} ({agent.id})")

        await db.commit()
    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Smart Assistant test agent")
    parser.add_argument("--org-id", required=True, help="Organisation ID to seed agents into")
    args = parser.parse_args()

    print(f"Seeding agents into org {args.org_id}…\n")
    asyncio.run(seed(args.org_id))


if __name__ == "__main__":
    main()
