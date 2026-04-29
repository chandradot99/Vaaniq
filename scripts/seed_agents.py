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

from naaviq.server.core.database import async_session_factory
import naaviq.server.auth.models  # noqa: F401  — ensures FK tables are loaded
from naaviq.server.agents.models import Agent

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

AGENTS = [
    # ------------------------------------------------------------------
    # Personal Google Assistant — Calendar + Gmail tools via condition
    # routing, collect_data, and goto loops. Voice-optimized: voice-
    # friendly prompts (no bullet points), all required fields enforced.
    # Booking flow includes a confirmation step (llm_response reads all
    # collected fields dynamically) before creating the calendar event.
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
                        # Short, voice-friendly greeting — no bullet points or newlines
                        # that TTS would read literally.
                        "greeting": (
                            "Hi! I'm your personal Google assistant. "
                            "I can book meetings, check your schedule, or send emails. "
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
                        "provider": "openai",
                        "model": "gpt-4o-mini",
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
                # collect_data gathers all required fields one at a time.
                # Pre-extraction pass skips questions for info the user
                # already provided upfront (e.g. "book tomorrow 9pm with Rahul").
                # end_datetime is required so {{collected.end_datetime}} is
                # always populated for both create_event and send_invite.
                {
                    "id": "collect_booking",
                    "type": "collect_data",
                    "label": "Collect Booking Details",
                    "position": {"x": 750, "y": 80},
                    "config": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "instructions": (
                            "The user wants to book a calendar meeting. Extract whatever they "
                            "already mentioned (title, attendee, date/time) so we can skip asking "
                            "for it. Dates and times may be informal (e.g. 'tomorrow 10pm', "
                            "'next Monday 3-4pm') — resolve to YYYY-MM-DDTHH:MM format. "
                            "For emails, ask the user to spell it out if unclear."
                        ),
                        "fields": [
                            {
                                "name": "meeting_title",
                                "type": "string",
                                "prompt": "What is the meeting about?",
                                "required": True,
                            },
                            {
                                "name": "attendee_name",
                                "type": "string",
                                "prompt": "Who are you meeting with?",
                                "required": True,
                            },
                            {
                                "name": "attendee_email",
                                "type": "email",
                                "prompt": "What is their email address? Please spell it out.",
                                "required": True,
                                "validation_prompt": "Must be a valid email address, e.g. name@domain.com.",
                            },
                            {
                                "name": "start_datetime",
                                "type": "date",
                                "prompt": "What date and time should it start?",
                                "required": True,
                                "validation_prompt": "Resolve to YYYY-MM-DDTHH:MM using today as reference.",
                            },
                            {
                                "name": "end_datetime",
                                "type": "date",
                                "prompt": "What time does it end? You can also say 'one hour later'.",
                                "required": True,
                                "validation_prompt": (
                                    "Resolve to YYYY-MM-DDTHH:MM. "
                                    "If the user says 'one hour later', add 1 hour to start_datetime."
                                ),
                            },
                        ],
                    },
                },
                # llm_response: reads all collected fields from state and
                # summarises them for the user before booking. The LLM has
                # access to state["collected"] so it can mention every field
                # dynamically — impossible with a static collect_data prompt.
                {
                    "id": "confirm_details",
                    "type": "llm_response",
                    "label": "Confirm Details",
                    "position": {"x": 1050, "y": 80},
                    "config": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "instructions": (
                            "You have just collected all the booking details from the user. "
                            "Read them from the collected fields in the session state and "
                            "summarise them in one short, friendly sentence — for example: "
                            "'Just to confirm: I'll book a dinner with Rahul at rahul@example.com "
                            "on April 10th from 9 PM to 10 PM. Does that sound right?' "
                            "Do not proceed with the booking yet — only ask for confirmation."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                # inbound_message: waits for the user's yes/no response.
                {
                    "id": "confirm_wait",
                    "type": "inbound_message",
                    "label": "Wait for Confirmation",
                    "position": {"x": 1300, "y": 80},
                    "config": {},
                },
                # condition: routes "yes" → create event, "no" → re-collect.
                # Both outgoing edges MUST use the "condition" key — mixing
                # add_edge and add_conditional_edges on the same source node
                # causes both branches to fire simultaneously.
                {
                    "id": "confirm_route",
                    "type": "condition",
                    "label": "Confirmed?",
                    "position": {"x": 1550, "y": 80},
                    "config": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "router_prompt": "Did the user confirm the booking details are correct?",
                        "routes": [
                            {
                                "label": "yes",
                                "description": "User said yes, correct, confirmed, go ahead, or similar",
                            },
                            {
                                "label": "no",
                                "description": "User said no, wrong, incorrect, change, or wants to modify details",
                            },
                        ],
                    },
                },
                # run_tool: creates the calendar event from confirmed collected fields.
                {
                    "id": "create_event",
                    "type": "run_tool",
                    "label": "Create Calendar Event",
                    "position": {"x": 1800, "y": 20},
                    "config": {
                        "tool": "google_calendar_create_event",
                        "input": {
                            "title": "{{collected.meeting_title}}",
                            "start_time": "{{collected.start_datetime}}",
                            "end_time": "{{collected.end_datetime}}",
                            "attendees": ["{{collected.attendee_email}}"],
                            "timezone": "Asia/Kolkata",
                        },
                    },
                },
                # run_tool: sends a confirmation email to the attendee.
                {
                    "id": "send_invite",
                    "type": "run_tool",
                    "label": "Send Invite Email",
                    "position": {"x": 1800, "y": 160},
                    "config": {
                        "tool": "gmail_send_email",
                        "input": {
                            "to": "{{collected.attendee_email}}",
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
                # llm_response: no tools — only generates the post-booking message.
                {
                    "id": "confirm_booking",
                    "type": "llm_response",
                    "label": "Confirm Booking",
                    "position": {"x": 2050, "y": 80},
                    "config": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "instructions": (
                            "The calendar event has been created and a confirmation email has "
                            "been sent to the attendee. Write a short, friendly confirmation — "
                            "mention the meeting title and time. "
                            "Ask if there is anything else you can help with."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                # ── Check schedule branch ──────────────────────────────
                {
                    "id": "list_events",
                    "type": "run_tool",
                    "label": "Fetch Calendar Events",
                    "position": {"x": 750, "y": 320},
                    "config": {
                        "tool": "google_calendar_list_events",
                        "input": {
                            "days_ahead": 7,
                            "max_results": 10,
                        },
                        "save_response_to": "rag_context",
                    },
                },
                {
                    "id": "show_schedule",
                    "type": "llm_response",
                    "label": "Show Schedule",
                    "position": {"x": 1050, "y": 320},
                    "config": {
                        "instructions": (
                            "The user's upcoming Google Calendar events have just been fetched "
                            "and are available in your context. "
                            "Format them into a clean, readable list — show each event's title, "
                            "date, and time. If the calendar is empty, say so. "
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
                    "label": "Collect Email Details",
                    "position": {"x": 750, "y": 520},
                    "config": {
                        "fields": [
                            {
                                "name": "email_to",
                                "type": "email",
                                "prompt": "Who should I send it to? Please spell out their email address.",
                                "required": True,
                                "validation_prompt": "Must be a valid email address.",
                            },
                            {
                                "name": "email_subject",
                                "type": "string",
                                "prompt": "What is the subject?",
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
                {
                    "id": "send_email",
                    "type": "run_tool",
                    "label": "Send Email",
                    "position": {"x": 1050, "y": 520},
                    "config": {
                        "tool": "gmail_send_email",
                        "input": {
                            "to": "{{collected.email_to}}",
                            "subject": "{{collected.email_subject}}",
                            "body": "{{collected.email_body}}",
                        },
                    },
                },
                {
                    "id": "confirm_email",
                    "type": "llm_response",
                    "label": "Confirm Email Sent",
                    "position": {"x": 1300, "y": 520},
                    "config": {
                        "instructions": (
                            "The email has just been sent successfully. "
                            "Confirm to the user — mention the recipient and subject. "
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
                {"id": "e1", "source": "start", "target": "wait"},
                {"id": "e2", "source": "wait", "target": "route"},
                # Routing
                {
                    "id": "e3",
                    "source": "route",
                    "target": "collect_booking",
                    "condition": "book_meeting",
                },
                {
                    "id": "e4",
                    "source": "route",
                    "target": "list_events",
                    "condition": "check_schedule",
                },
                {
                    "id": "e5",
                    "source": "route",
                    "target": "collect_email",
                    "condition": "send_email",
                },
                {
                    "id": "e6",
                    "source": "route",
                    "target": "farewell",
                    "condition": "end",
                },
                # Book meeting: collect → confirm details → wait → route → create → send → done
                # "no" route loops back to collect_booking to re-gather fields.
                # All edges out of confirm_route use "condition" key — never mix
                # add_edge and add_conditional_edges on the same source node.
                {"id": "e7", "source": "collect_booking", "target": "confirm_details"},
                {"id": "e8", "source": "confirm_details", "target": "confirm_wait"},
                {"id": "e9", "source": "confirm_wait", "target": "confirm_route"},
                {
                    "id": "e10",
                    "source": "confirm_route",
                    "target": "create_event",
                    "condition": "yes",
                },
                {
                    "id": "e11",
                    "source": "confirm_route",
                    "target": "collect_booking",
                    "condition": "no",
                    "goto": True,
                    "goto_node_position": {"x": 1700, "y": 80},
                },
                {"id": "e12", "source": "create_event", "target": "send_invite"},
                {"id": "e13", "source": "send_invite", "target": "confirm_booking"},
                {
                    "id": "e14",
                    "source": "confirm_booking",
                    "target": "wait",
                    "goto": True,
                    "goto_node_position": {"x": 2250, "y": 80},
                },
                # Check schedule: fetch → format → loop
                {"id": "e15", "source": "list_events", "target": "show_schedule"},
                {
                    "id": "e16",
                    "source": "show_schedule",
                    "target": "wait",
                    "goto": True,
                    "goto_node_position": {"x": 1250, "y": 320},
                },
                # Send email: collect → send → confirm → loop
                {"id": "e17", "source": "collect_email", "target": "send_email"},
                {"id": "e18", "source": "send_email", "target": "confirm_email"},
                {
                    "id": "e19",
                    "source": "confirm_email",
                    "target": "wait",
                    "goto": True,
                    "goto_node_position": {"x": 1500, "y": 520},
                },
            ],
        },
    }
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
    parser.add_argument(
        "--org-id", required=True, help="Organisation ID to seed agents into"
    )
    args = parser.parse_args()

    print(f"Seeding agents into org {args.org_id}…\n")
    asyncio.run(seed(args.org_id))


if __name__ == "__main__":
    main()
