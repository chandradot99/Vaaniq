"""
Unit tests for LangGraphLLM — the LiveKit LLM adapter.

All LangGraph internals are mocked — no DB or real graph needed.

Key behaviors tested:
- Turn 0 (greeting): graph invoked with initial_state
- Turn N (user spoke): graph resumed with Command(resume=user_text)
- Streaming tokens emitted as ChatChunk objects
- Internal node filtering (condition, collect_data, human_review)
- Non-streaming fallback: nodes without LLM use state/interrupt text
- Empty user text on turn N+: no graph call, stream ends cleanly
"""

from unittest.mock import AsyncMock, MagicMock

from livekit.agents import llm

from naaviq.voice.llm.langgraph import (
    LangGraphLLM,
    _extract_agent_text,
    _extract_interrupt_text,
    _extract_user_text,
)

# ── Test data ─────────────────────────────────────────────────────────────────

GRAPH_CONFIG = {
    "nodes": [
        {"id": "greet",   "type": "llm_response"},
        {"id": "route",   "type": "condition"},
        {"id": "collect", "type": "collect_data"},
        {"id": "review",  "type": "human_review"},
        {"id": "end",     "type": "end_session"},
    ],
    "edges": [],
    "entry_point": "greet",
}

# Config with a real start node (has greeting) — used for greeting tests
GRAPH_CONFIG_WITH_START = {
    "nodes": [
        {
            "id": "start",
            "type": "start",
            "config": {"system_message": "You are helpful.", "greeting": "Hello! How can I help?"},
        },
        {"id": "wait",    "type": "inbound_message"},
        {"id": "respond", "type": "llm_response"},
        {"id": "route",   "type": "condition"},
        {"id": "collect", "type": "collect_data"},
        {"id": "review",  "type": "human_review"},
        {"id": "end",     "type": "end_session"},
    ],
    "edges": [],
    "entry_point": "start",
}

INITIAL_STATE = {
    "session_id": "sess-1",
    "agent_id": "agent-1",
    "org_id": "org-1",
    "channel": "voice",
    "user_id": "+919876543210",
    "messages": [],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_interrupt(content: str | None = None) -> MagicMock:
    ivr = MagicMock()
    ivr.value = {"content": content} if content is not None else {}
    return ivr


def _make_state_snapshot(interrupt_content: str | None = None, session_ended: bool = False) -> MagicMock:
    snap = MagicMock()
    snap.values = {"session_ended": session_ended}
    if interrupt_content is not None:
        task = MagicMock()
        task.interrupts = [_make_interrupt(interrupt_content)]
        snap.tasks = [task]
    else:
        snap.tasks = []
    return snap


def _make_chunk(content: str, node_id: str = "greet") -> dict:
    """Build a mock on_chat_model_stream event."""
    chunk = MagicMock()
    chunk.content = content
    return {
        "event": "on_chat_model_stream",
        "metadata": {"langgraph_node": node_id},
        "data": {"chunk": chunk},
    }


def _make_astream(*events):
    """
    Return an async generator function suitable for MagicMock(side_effect=...).

    Usage:
        graph.astream_events = MagicMock(side_effect=_make_astream(event1, event2))

    When called, the side_effect function is invoked with the same args as the
    mock, so calling graph.astream_events(...) returns an async generator.
    """
    async def gen(*args, **kwargs):
        for event in events:
            yield event
    return gen


def _make_llm(graph=None, graph_config=None) -> LangGraphLLM:
    return LangGraphLLM(
        graph=graph or MagicMock(),
        thread_id="sess-1",
        initial_state=INITIAL_STATE,
        graph_config=graph_config or GRAPH_CONFIG,
    )


async def _advance_turn0(adapter: LangGraphLLM) -> None:
    """Consume turn 0 (greeting) so subsequent tests can exercise turn N."""
    stream0 = adapter.chat(chat_ctx=_make_chat_ctx())
    async with stream0:
        async for _ in stream0:
            pass


def _make_chat_ctx(user_text: str | None = None) -> llm.ChatContext:
    ctx = llm.ChatContext()
    if user_text:
        ctx.add_message(role="user", content=user_text)
    return ctx


# ── _extract_user_text ────────────────────────────────────────────────────────

def test_extract_user_text_returns_last_user_message():
    ctx = _make_chat_ctx("hello there")
    assert _extract_user_text(ctx) == "hello there"


def test_extract_user_text_empty_when_no_user_message():
    ctx = _make_chat_ctx()
    assert _extract_user_text(ctx) == ""


def test_extract_user_text_returns_last_when_multiple():
    ctx = llm.ChatContext()
    ctx.add_message(role="user", content="first")
    ctx.add_message(role="assistant", content="response")
    ctx.add_message(role="user", content="second")
    assert _extract_user_text(ctx) == "second"


# ── _extract_agent_text ───────────────────────────────────────────────────────

def test_extract_agent_text_from_state():
    state = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "agent", "content": "Hello! How can I help?"},
        ]
    }
    assert _extract_agent_text(state) == "Hello! How can I help?"


def test_extract_agent_text_empty_when_no_agent_message():
    assert _extract_agent_text({}) == ""
    assert _extract_agent_text({"messages": []}) == ""


# ── _extract_interrupt_text ───────────────────────────────────────────────────

def test_extract_interrupt_text_returns_content():
    snap = _make_state_snapshot("What is your name?")
    assert _extract_interrupt_text(snap) == "What is your name?"


def test_extract_interrupt_text_empty_when_no_interrupt():
    snap = _make_state_snapshot()
    assert _extract_interrupt_text(snap) == ""


def test_extract_interrupt_text_empty_on_none_snapshot():
    assert _extract_interrupt_text(None) == ""


# ── LangGraphLLM.chat() ───────────────────────────────────────────────────────

async def test_chat_returns_stream():
    adapter = _make_llm()
    stream = adapter.chat(chat_ctx=_make_chat_ctx())
    from naaviq.voice.llm.langgraph import LangGraphLLMStream
    assert isinstance(stream, LangGraphLLMStream)
    await stream.aclose()


async def test_chat_increments_turn_counter():
    adapter = _make_llm()
    assert adapter._turn == 0
    s1 = adapter.chat(chat_ctx=_make_chat_ctx())
    assert adapter._turn == 1
    s2 = adapter.chat(chat_ctx=_make_chat_ctx())
    assert adapter._turn == 2
    await s1.aclose()
    await s2.aclose()


def test_internal_node_ids_computed_correctly():
    adapter = _make_llm()
    assert adapter._internal_node_ids == {"route", "collect", "review"}
    assert "greet" not in adapter._internal_node_ids
    assert "end" not in adapter._internal_node_ids


# ── LangGraphLLMStream._run() — turn 0 (greeting) ────────────────────────────

async def test_run_turn0_emits_greeting_from_config():
    """Turn 0 emits the greeting from the start node config — not from graph events."""
    graph = MagicMock()
    # Graph events on turn 0 are consumed but NOT streamed to TTS
    graph.astream_events = MagicMock(side_effect=_make_astream(_make_chunk("graph-token")))
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    adapter = _make_llm(graph, graph_config=GRAPH_CONFIG_WITH_START)
    stream = adapter.chat(chat_ctx=_make_chat_ctx())  # turn 0

    chunks = []
    async with stream:
        async for chunk in stream:
            chunks.append(chunk)

    # graph is called with initial_state to advance to the inbound_message interrupt
    call_args = graph.astream_events.call_args[0][0]
    assert call_args == INITIAL_STATE
    # Greeting comes from config, not from the graph events
    contents = [c.delta.content for c in chunks]
    assert "Hello! How can I help?" in contents   # from start node config
    assert "graph-token" not in contents          # graph events NOT streamed on turn 0


async def test_run_turn0_no_greeting_when_config_has_none():
    """Turn 0 emits nothing when the start node has no greeting configured."""
    graph = MagicMock()
    graph.astream_events = MagicMock(side_effect=_make_astream(_make_chunk("should-not-appear")))
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    # GRAPH_CONFIG has no start node with greeting
    adapter = _make_llm(graph, graph_config=GRAPH_CONFIG)
    stream = adapter.chat(chat_ctx=_make_chat_ctx())

    chunks = []
    async with stream:
        async for chunk in stream:
            chunks.append(chunk)

    assert chunks == []  # no greeting, no graph event streaming on turn 0


async def test_run_turn1_invokes_graph_with_command():
    from langgraph.types import Command

    graph = MagicMock()
    graph.astream_events = MagicMock(
        side_effect=_make_astream(_make_chunk("Nice to meet you."))
    )
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    adapter = _make_llm(graph)
    # Advance past turn 0
    stream0 = adapter.chat(chat_ctx=_make_chat_ctx())
    async with stream0:
        async for _ in stream0:
            pass

    stream1 = adapter.chat(chat_ctx=_make_chat_ctx("My name is Rahul"))
    chunks = []
    async with stream1:
        async for chunk in stream1:
            chunks.append(chunk)

    call_args = graph.astream_events.call_args[0][0]
    assert isinstance(call_args, Command)
    assert call_args.resume == "My name is Rahul"
    assert any(c.delta.content == "Nice to meet you." for c in chunks)


# ── Internal node filtering ───────────────────────────────────────────────────

async def test_internal_node_tokens_not_emitted():
    """Tokens from condition/collect_data/human_review must not reach TTS (turn 1)."""
    graph = MagicMock()
    graph.astream_events = MagicMock(
        side_effect=_make_astream(
            _make_chunk("internal routing token", node_id="route"),    # filtered
            _make_chunk("also internal",           node_id="collect"), # filtered
            _make_chunk("Hello, how can I help?",  node_id="greet"),   # allowed
        )
    )
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    adapter = _make_llm(graph)
    await _advance_turn0(adapter)  # consume turn 0

    stream = adapter.chat(chat_ctx=_make_chat_ctx("hi"))  # turn 1
    chunks = []
    async with stream:
        async for chunk in stream:
            chunks.append(chunk)

    contents = [c.delta.content for c in chunks]
    assert "internal routing token" not in contents
    assert "also internal" not in contents
    assert "Hello, how can I help?" in contents


# ── Non-streaming fallback ────────────────────────────────────────────────────

async def test_non_streaming_fallback_uses_interrupt_text():
    """When no on_chat_model_stream events fire on turn 1, use active interrupt text."""
    graph = MagicMock()
    # No streaming events
    graph.astream_events = MagicMock(side_effect=_make_astream())
    graph.aget_state = AsyncMock(
        return_value=_make_state_snapshot("What is your budget?")
    )

    adapter = _make_llm(graph)
    await _advance_turn0(adapter)  # consume turn 0

    stream = adapter.chat(chat_ctx=_make_chat_ctx("I want to buy something"))  # turn 1
    chunks = []
    async with stream:
        async for chunk in stream:
            chunks.append(chunk)

    assert any("What is your budget?" in c.delta.content for c in chunks)


async def test_non_streaming_fallback_uses_agent_state_message():
    """When no interrupt on turn 1, fall back to agent message from final state."""
    graph = MagicMock()
    graph.astream_events = MagicMock(
        side_effect=_make_astream(
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [{"role": "agent", "content": "Goodbye!"}]
                    }
                },
            }
        )
    )
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    adapter = _make_llm(graph)
    await _advance_turn0(adapter)  # consume turn 0

    stream = adapter.chat(chat_ctx=_make_chat_ctx("bye"))  # turn 1
    chunks = []
    async with stream:
        async for chunk in stream:
            chunks.append(chunk)

    assert any("Goodbye!" in c.delta.content for c in chunks)


async def test_session_ended_triggers_callback():
    """When graph sets session_ended=True, the on_session_ended callback is called.

    session_ended is detected via aget_state() after the event loop, not via
    on_chain_end events (which are unreliable for state flags).
    """
    graph = MagicMock()
    graph.astream_events = MagicMock(side_effect=_make_astream())  # no events needed
    # aget_state reports session_ended=True — this is the detection source
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot(session_ended=True))

    callback_called = False

    async def _on_ended():
        nonlocal callback_called
        callback_called = True

    adapter = LangGraphLLM(
        graph=graph,
        thread_id="sess-1",
        initial_state=INITIAL_STATE,
        graph_config=GRAPH_CONFIG,
        on_session_ended=_on_ended,
    )
    await _advance_turn0(adapter)  # consume turn 0

    stream = adapter.chat(chat_ctx=_make_chat_ctx("thank you"))  # turn 1
    async with stream:
        async for _ in stream:
            pass

    # asyncio.create_task schedules the callback — wait for it
    import asyncio
    await asyncio.sleep(0)
    assert callback_called


# ── Empty user text (turn N) ──────────────────────────────────────────────────

async def test_empty_user_text_on_turn1_produces_no_chunks():
    """Turn 1 with empty user text should not call graph and emit nothing."""
    graph = MagicMock()
    graph.astream_events = MagicMock(side_effect=_make_astream(_make_chunk("Hi!")))
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot())

    adapter = _make_llm(graph)
    # Complete turn 0
    stream0 = adapter.chat(chat_ctx=_make_chat_ctx())
    async with stream0:
        async for _ in stream0:
            pass

    graph.astream_events.reset_mock()

    # Turn 1 with no user text
    stream1 = adapter.chat(chat_ctx=_make_chat_ctx())  # no user message
    chunks = []
    async with stream1:
        async for chunk in stream1:
            chunks.append(chunk)

    graph.astream_events.assert_not_called()
    assert chunks == []
