"""
ChatService — runs agent graphs for text chat sessions.

Uses AsyncPostgresSaver (via chat/checkpointer.py) so conversation state
survives server restarts. Session metadata (transcript, status) is stored
in the sessions table via SessionRepository.

Multi-turn flow:
  start()   → graph.ainvoke(initial_state)     → graph runs until interrupt or END
  message() → graph.ainvoke(Command(resume=…)) → graph resumes until next interrupt or END

Interrupt types surfaced to the frontend:
  {"type": "user_input"}                           — inbound_message node waiting (no agent msg)
  {"type": "collect_question", "content": "…"}    — collect_data asking for a field
  {"type": "human_review", "message": "…", ...}   — human_review node waiting for approval
"""
import json
import os
import structlog
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.graph.builder import GraphBuilder
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.chat.checkpointer import get_checkpointer, make_thread_id
from vaaniq.server.chat.exceptions import ChatSessionNotFound, ChatSessionEnded
from vaaniq.server.chat.repository import SessionRepository
from vaaniq.server.chat.schemas import ChatMessage, StartChatResponse, SendMessageResponse
from vaaniq.server.chat.tracing import TurnEventCollector, SessionEventRepository

log = structlog.get_logger()


# ── LangSmith run capture ─────────────────────────────────────────────────────


def _langsmith_enabled() -> bool:
    return bool(os.environ.get("LANGSMITH_API_KEY"))


class _RunIdCapture(BaseCallbackHandler):
    """Captures the root LangGraph run ID for LangSmith URL lookup."""

    def __init__(self) -> None:
        super().__init__()
        self.run_id: str | None = None

    def on_chain_start(self, serialized: dict, inputs: dict, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs) -> None:  # noqa: ARG002
        if parent_run_id is None:
            self.run_id = str(run_id)


def _fetch_langsmith_url(run_id: str) -> str | None:
    """Return the LangSmith URL for a run ID. Returns None on any failure."""
    try:
        from langsmith import Client
        run = Client().read_run(UUID(run_id))
        return run.url
    except Exception:
        return None


def _langsmith_config(base_config: dict, session_id: str, agent_id: str, capture: _RunIdCapture, extra_callbacks: list | None = None) -> dict:
    """Augment a LangGraph config with LangSmith tags and the run capture callback."""
    extra: dict = {
        "run_name": f"session:{session_id[:8]}",
        "tags": [f"session_id:{session_id}", f"agent_id:{agent_id}"],
        "metadata": {"session_id": session_id, "agent_id": agent_id},
    }
    callbacks: list = extra_callbacks or []
    if _langsmith_enabled():
        callbacks = [capture] + callbacks
    if callbacks:
        extra["callbacks"] = callbacks
    return {**base_config, **extra}


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_org_keys(org_id: str, db: AsyncSession) -> dict:
    from vaaniq.server.integrations.service import PostgresCredentialStore
    return await PostgresCredentialStore(db).get_org_keys(org_id)


def _extract_new_agent_messages(all_messages: list[dict], cursor: int) -> list[ChatMessage]:
    return [
        ChatMessage(role=m["role"], content=m["content"])
        for m in all_messages[cursor:]
        if m["role"] == "agent"
    ]


async def _get_interrupt_info(graph, config: dict) -> dict | None:
    """Return the interrupt value from the current paused task, or None."""
    state_info = await graph.aget_state(config)
    for task in state_info.tasks:
        for intr in task.interrupts:
            if isinstance(intr.value, dict):
                return intr.value
    return None


def _make_interrupt_message(interrupt_info: dict) -> ChatMessage | None:
    """Convert an interrupt payload into a ChatMessage for the frontend, if applicable."""
    itype = interrupt_info.get("type")
    if itype == "collect_question":
        return ChatMessage(role="agent", content=interrupt_info.get("content", ""))
    if itype == "human_review":
        return ChatMessage(role="agent", content=json.dumps(interrupt_info))
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
        "whisper_message": None,
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


def _turn_number(session_meta: dict | None) -> int:
    """0-based turn index read from session.meta['turn_count'] (persisted across send_message calls).

    Replaces the old transcript-length heuristic which broke during collect_data
    because the transcript doesn't grow until the node returns.
    """
    return (session_meta or {}).get("turn_count", 0)


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
    checkpointer = get_checkpointer()
    graph = await GraphBuilder().build(agent.graph_config, org_keys, checkpointer)

    # Persist session record before invoking the graph
    session_repo = SessionRepository(db)
    session = await session_repo.create(org_id=org_id, agent_id=agent_id)
    await db.flush()  # get session.id without committing
    session_id = session.id

    thread_id = make_thread_id(org_id, session_id)
    base_config = {"configurable": {"thread_id": thread_id}}
    capture = _RunIdCapture()
    collector = TurnEventCollector(session_id, turn=0, graph_config=agent.graph_config)
    config = _langsmith_config(base_config, session_id, agent_id, capture, extra_callbacks=[collector.as_callback_handler()])

    result = await graph.ainvoke(_initial_state(session_id, agent_id, org_id), config=config)

    session_ended: bool = result.get("session_ended", False)
    all_messages: list[dict] = result.get("messages", [])
    new_msgs = _extract_new_agent_messages(all_messages, 0)

    langsmith_url = _fetch_langsmith_url(capture.run_id) if capture.run_id else None

    # turn_count=1 after start_session (turn 0 just ran)
    _base_meta: dict = {"turn_count": 1}
    if langsmith_url:
        _base_meta["langsmith_url"] = langsmith_url

    if not session_ended:
        interrupt_info = await _get_interrupt_info(graph, base_config)
        if interrupt_info:
            msg = _make_interrupt_message(interrupt_info)
            if msg:
                new_msgs.append(msg)
            collector.add_interrupt(interrupt_info)
        await session_repo.update_transcript(
            session_id, transcript=all_messages, tool_calls=result.get("tool_calls", []),
            meta=_base_meta,
        )
    else:
        await session_repo.mark_ended(
            session_id,
            transcript=all_messages,
            tool_calls=result.get("tool_calls", []),
            meta=_base_meta,
        )

    await SessionEventRepository(db).bulk_insert(collector.finalize())
    await db.commit()
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
    session_repo = SessionRepository(db)
    session = await session_repo.get(session_id)
    if not session:
        raise ChatSessionNotFound()
    if session.status == "ended":
        raise ChatSessionEnded()

    agent = await AgentRepository(db).get_by_id(session.agent_id)
    org_keys = await _get_org_keys(session.org_id, db)
    checkpointer = get_checkpointer()
    graph = await GraphBuilder().build(agent.graph_config, org_keys, checkpointer)

    thread_id = make_thread_id(session.org_id, session_id)
    base_config = {"configurable": {"thread_id": thread_id}}
    capture = _RunIdCapture()
    turn = _turn_number(session.meta)
    collector = TurnEventCollector(session_id, turn=turn, graph_config=agent.graph_config)
    config = _langsmith_config(base_config, session_id, session.agent_id, capture, extra_callbacks=[collector.as_callback_handler()])

    state_before = await graph.aget_state(base_config)
    cursor = len(state_before.values.get("messages", []))

    result = await graph.ainvoke(Command(resume=user_message), config=config)

    session_ended: bool = result.get("session_ended", False)
    all_messages: list[dict] = result.get("messages", [])
    new_msgs = _extract_new_agent_messages(all_messages, cursor)

    langsmith_url = _fetch_langsmith_url(capture.run_id) if capture.run_id else None
    _send_meta: dict = {"turn_count": turn + 1}
    if langsmith_url:
        _send_meta["langsmith_url"] = langsmith_url

    if not session_ended:
        interrupt_info = await _get_interrupt_info(graph, base_config)
        if interrupt_info:
            msg = _make_interrupt_message(interrupt_info)
            if msg:
                new_msgs.append(msg)
            collector.add_interrupt(interrupt_info)
        await session_repo.update_transcript(
            session_id, transcript=all_messages, tool_calls=result.get("tool_calls", []),
            meta=_send_meta,
        )
    else:
        await session_repo.mark_ended(
            session_id,
            transcript=all_messages,
            tool_calls=result.get("tool_calls", []),
            meta=_send_meta,
        )

    await SessionEventRepository(db).bulk_insert(collector.finalize())
    await db.commit()
    log.info("chat_message_processed", session_id=session_id, session_ended=session_ended)

    return SendMessageResponse(messages=new_msgs, session_ended=session_ended)


# ── Streaming send ────────────────────────────────────────────────────────────


def _sse(event_type: str, payload: dict) -> str:
    """Format a single SSE event line."""
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


async def stream_message(
    session_id: str,
    user_message: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Yield SSE events for a single user turn.

    Event types:
        token        — LLM text chunk (stream_mode="messages")
        node_start   — graph node began executing
        node_end     — graph node finished
        node_message — agent message not streamed via tokens (node errors, farewell,
                       transfer hold message); includes content + node_id
        human_review — graph paused waiting for approval
        collect_question — collect_data asking for a field value
        ended        — turn complete; includes session_ended flag
        error        — session not found / already ended / unhandled exception
    """
    session_repo = SessionRepository(db)
    session = await session_repo.get(session_id)
    if not session:
        yield _sse("error", {"message": "Session not found"})
        return
    if session.status == "ended":
        yield _sse("error", {"message": "Session has already ended"})
        return

    agent = await AgentRepository(db).get_by_id(session.agent_id)
    org_keys = await _get_org_keys(session.org_id, db)
    checkpointer = get_checkpointer()
    graph = await GraphBuilder().build(agent.graph_config, org_keys, checkpointer)

    thread_id = make_thread_id(session.org_id, session_id)
    base_config = {"configurable": {"thread_id": thread_id}}
    capture = _RunIdCapture()
    turn = _turn_number(session.meta)
    collector = TurnEventCollector(session_id, turn=turn, graph_config=agent.graph_config)
    config = _langsmith_config(base_config, session_id, session.agent_id, capture)

    # Node types whose LLM calls are internal (routing, review) — never stream their tokens
    _INTERNAL_LLM_TYPES = {"condition", "human_review", "collect_data"}
    _internal_node_ids = {
        node["id"]
        for node in (agent.graph_config.get("nodes", []) if agent.graph_config else [])
        if node.get("type") in _INTERNAL_LLM_TYPES
    }

    # Nodes we don't want to surface as node_start/end events (LangGraph internals)
    _SKIP_NODES = {"LangGraph", "__start__", ""}

    # Capture state snapshot before stream begins so we can detect new errors afterward.
    # Errors are stored in state["error"] (not in messages) so voice/LLM never sees them.
    state_before_stream = await graph.aget_state(base_config)
    error_before = state_before_stream.values.get("error")

    try:
        async for event in graph.astream_events(
            Command(resume=user_message),
            config=config,
            version="v2",
        ):
            kind: str = event["event"]
            name: str = event.get("name", "")

            # Feed every event into the collector (pure in-memory, no I/O)
            collector.ingest(event)

            if kind == "on_chat_model_stream":
                # Skip tokens from internal routing/review nodes
                langgraph_node = event.get("metadata", {}).get("langgraph_node", "")
                if langgraph_node in _internal_node_ids:
                    continue
                chunk = event["data"].get("chunk")
                if chunk and getattr(chunk, "content", None):
                    yield _sse("token", {"content": chunk.content})

            elif kind == "on_chain_start" and name not in _SKIP_NODES:
                yield _sse("node_start", {"node": name})

            elif kind == "on_chain_end" and name not in _SKIP_NODES:
                output = event.get("data", {}).get("output")
                node_error = output.get("error") if isinstance(output, dict) else None
                yield _sse("node_end", {"node": name, "error": node_error})

    except Exception as exc:
        log.error("chat_stream_error", session_id=session_id, error=str(exc))
        collector.add_error(exc)
        await SessionEventRepository(db).bulk_insert(collector.finalize())
        await db.commit()
        yield _sse("error", {"message": "An error occurred during processing"})
        return

    # After stream ends, inspect state for interrupts (human_review, collect_data)
    state_after = await graph.aget_state(base_config)
    interrupt_info: dict | None = None
    for task in (state_after.tasks or []):
        for intr in (getattr(task, "interrupts", None) or []):
            if isinstance(intr.value, dict):
                interrupt_info = intr.value
                break

    if interrupt_info:
        collector.add_interrupt(interrupt_info)
        itype = interrupt_info.get("type", "interrupt")
        yield _sse(itype, interrupt_info)

    state_values = state_after.values or {}
    session_ended: bool = state_values.get("session_ended", False)
    all_messages = state_values.get("messages", [])

    # Surface any new node error to the debug panel via node_message SSE.
    # Errors live in state["error"] — never in state["messages"] — so voice/TTS
    # and the LLM conversation history are always clean.
    new_error = state_values.get("error")
    if new_error and new_error != error_before:
        yield _sse("node_message", {"content": new_error, "is_error": True})

    langsmith_url = _fetch_langsmith_url(capture.run_id) if capture.run_id else None
    _stream_meta: dict = {"turn_count": turn + 1}
    if langsmith_url:
        _stream_meta["langsmith_url"] = langsmith_url

    if session_ended:
        await session_repo.mark_ended(
            session_id,
            transcript=all_messages,
            tool_calls=state_values.get("tool_calls", []),
            meta=_stream_meta,
        )
    else:
        await session_repo.update_transcript(
            session_id,
            transcript=all_messages,
            tool_calls=state_values.get("tool_calls", []),
            meta=_stream_meta,
        )

    await SessionEventRepository(db).bulk_insert(collector.finalize())
    await db.commit()

    yield _sse("ended", {"session_ended": session_ended})
    log.info("chat_stream_complete", session_id=session_id, session_ended=session_ended)
