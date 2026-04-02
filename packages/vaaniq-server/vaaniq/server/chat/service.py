"""
ChatService — runs agent graphs for text chat sessions (dev/testing).

Uses InMemorySaver as checkpointer so no extra DB table is needed.
The module-level singletons (_checkpointer, _sessions) live for the
lifetime of the server process — this is intentional for testing.
For production, replace InMemorySaver with AsyncPostgresSaver and
store session metadata in Redis.

Multi-turn flow:
  start()   → graph.ainvoke(initial_state)     → graph runs until interrupt or END
  message() → graph.ainvoke(Command(resume=…)) → graph resumes until next interrupt or END

Interrupt types:
  {"type": "user_input"}       — inbound_message node waiting for user (no agent msg to show)
  {"type": "collect_question", "content": "…"} — collect_data asking for a field (show as agent msg)
"""

import uuid
import structlog
from datetime import datetime, timezone

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.graph.builder import GraphBuilder
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.api_keys.repository import ApiKeyRepository
from vaaniq.server.core.encryption import decrypt_key
from vaaniq.server.chat.exceptions import ChatSessionNotFound, ChatSessionEnded
from vaaniq.server.chat.schemas import ChatMessage, StartChatResponse, SendMessageResponse

log = structlog.get_logger()

# ── Module-level state (dev/testing) ─────────────────────────────────────────
_checkpointer = InMemorySaver()

# session_id → {agent_id, org_id, ended}
_sessions: dict[str, dict] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_org_keys(org_id: str, db: AsyncSession) -> dict:
    """Return decrypted BYOK keys for the org as {service: plaintext_key}."""
    keys = await ApiKeyRepository(db).list_by_org(org_id)
    return {k.service: decrypt_key(k.encrypted_key) for k in keys}


def _extract_new_agent_messages(
    all_messages: list[dict],
    cursor: int,
) -> list[ChatMessage]:
    """Return agent messages added after cursor position."""
    return [
        ChatMessage(role=m["role"], content=m["content"])
        for m in all_messages[cursor:]
        if m["role"] == "agent"
    ]


async def _get_interrupt_agent_message(graph, config: dict) -> ChatMessage | None:
    """
    If the graph is currently interrupted, extract an agent-facing message
    from the interrupt value (used by collect_data questions).
    Returns None for inbound_message interrupts (no agent message to surface).
    """
    state_info = await graph.aget_state(config)
    for task in state_info.tasks:
        for intr in task.interrupts:
            v = intr.value
            if isinstance(v, dict) and v.get("type") == "collect_question":
                return ChatMessage(role="agent", content=v["content"])
    return None


def _initial_state(session_id: str, agent_id: str, org_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "org_id": org_id,
        "channel": "chat",
        "user_id": "web_user",
        "messages": [],
        "current_node": "",
        "route": None,
        "collected": {},
        "rag_context": "",
        "crm_record": None,
        "tool_calls": [],
        "transfer_to": None,
        "transfer_initiated": False,
        "start_time": now,
        "end_time": None,
        "duration_seconds": None,
        "session_ended": False,
        "summary": None,
        "sentiment": None,
        "action_items": [],
        "post_actions_completed": [],
        "error": None,
    }


# ── Service ───────────────────────────────────────────────────────────────────

async def start_session(
    agent_id: str,
    org_id: str,
    db: AsyncSession,
) -> StartChatResponse:
    agent = await AgentRepository(db).get_by_id(agent_id)
    if not agent or not agent.graph_config:
        raise ChatSessionNotFound()

    org_keys = await _get_org_keys(org_id, db)
    graph = await GraphBuilder().build(agent.graph_config, org_keys, _checkpointer)

    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    result = await graph.ainvoke(_initial_state(session_id, agent_id, org_id), config=config)

    session_ended: bool = result.get("session_ended", False)
    _sessions[session_id] = {"agent_id": agent_id, "org_id": org_id, "ended": session_ended}

    # Collect messages: agent messages now in state + possible collect_question interrupt
    all_messages: list[dict] = result.get("messages", [])
    new_msgs = _extract_new_agent_messages(all_messages, 0)

    if not session_ended:
        interrupt_msg = await _get_interrupt_agent_message(graph, config)
        if interrupt_msg:
            new_msgs.append(interrupt_msg)

    log.info("chat_session_started", session_id=session_id, agent_id=agent_id, org_id=org_id)

    return StartChatResponse(
        session_id=session_id,
        messages=new_msgs,
        session_ended=session_ended,
    )


async def send_message(
    session_id: str,
    user_message: str,
    db: AsyncSession,
) -> SendMessageResponse:
    session = _sessions.get(session_id)
    if not session:
        raise ChatSessionNotFound()
    if session["ended"]:
        raise ChatSessionEnded()

    agent = await AgentRepository(db).get_by_id(session["agent_id"])
    org_keys = await _get_org_keys(session["org_id"], db)
    graph = await GraphBuilder().build(agent.graph_config, org_keys, _checkpointer)

    config = {"configurable": {"thread_id": session_id}}

    # Note how many messages are in state before this turn
    state_before = await graph.aget_state(config)
    cursor = len(state_before.values.get("messages", []))

    result = await graph.ainvoke(Command(resume=user_message), config=config)

    session_ended: bool = result.get("session_ended", False)
    session["ended"] = session_ended

    all_messages: list[dict] = result.get("messages", [])
    new_msgs = _extract_new_agent_messages(all_messages, cursor)

    if not session_ended:
        interrupt_msg = await _get_interrupt_agent_message(graph, config)
        if interrupt_msg:
            new_msgs.append(interrupt_msg)

    log.info("chat_message_processed", session_id=session_id, session_ended=session_ended)

    return SendMessageResponse(messages=new_msgs, session_ended=session_ended)
