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
