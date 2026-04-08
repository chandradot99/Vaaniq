"""
Unit tests for VaaniqLangGraphService.

All LangGraph and Pipecat internals are mocked — no DB or real graph needed.

Key behaviors tested:
- Streaming tokens via astream_events (not ainvoke)
- Sentence boundary buffering — TTS gets complete sentences, not raw tokens
- Internal LLM node filtering (condition, collect_data, human_review)
- End-session fallback — nodes without LLM (end_session farewell) extracted from state
- session_ended / error detection via aget_state (not on_chain_end events)
- Turn counter management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pipecat.frames.frames import (
    EndFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from vaaniq.voice.services.langgraph_service import (
    VaaniqLangGraphService,
    _extract_user_text,
    _split_at_sentence_boundaries,
)


# ── Test data ─────────────────────────────────────────────────────────────────

GRAPH_CONFIG = {
    "nodes": [
        {"id": "greet",   "type": "llm_response"},
        {"id": "route",   "type": "condition"},       # internal — never stream
        {"id": "collect", "type": "collect_data"},    # internal — never stream
        {"id": "review",  "type": "human_review"},    # internal — never stream
        {"id": "end",     "type": "end_session"},     # no LLM — fallback path
    ],
    "edges": [],
    "entry_point": "greet",
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

def _make_state_snapshot(values: dict | None = None) -> MagicMock:
    """Mock StateSnapshot returned by graph.aget_state."""
    snap = MagicMock()
    snap.values = values or {}
    return snap


def _make_graph(stream=None, state_values: dict | None = None) -> MagicMock:
    """Build a graph mock with astream_events and aget_state set up."""
    graph = MagicMock()
    graph.astream_events = _async_iter(stream or _token_stream("Hello!"))
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot(state_values))
    return graph


def _make_service(graph=None) -> VaaniqLangGraphService:
    if graph is None:
        graph = _make_graph()
    svc = VaaniqLangGraphService(
        graph=graph,
        thread_id="org-1:sess-1",
        initial_state=INITIAL_STATE,
        graph_config=GRAPH_CONFIG,
    )
    return svc


def _async_iter(gen):
    """Wrap an async generator so it can be used as the return value of a MagicMock."""
    async def _inner(*args, **kwargs):
        async for item in gen:
            yield item
    return _inner


async def _token_stream(*texts: str, node: str = "greet"):
    """Async generator yielding on_chat_model_stream events."""
    for text in texts:
        chunk = MagicMock()
        chunk.content = text
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": node},
            "data": {"chunk": chunk},
        }


async def _internal_node_stream():
    """Mixed stream: one token from condition (filtered), one from greet (kept)."""
    chunk1 = MagicMock()
    chunk1.content = "routing decision"
    yield {
        "event": "on_chat_model_stream",
        "metadata": {"langgraph_node": "route"},   # internal — must be filtered
        "data": {"chunk": chunk1},
    }
    chunk2 = MagicMock()
    chunk2.content = "Hi there!"
    yield {
        "event": "on_chat_model_stream",
        "metadata": {"langgraph_node": "greet"},   # real response node — keep
        "data": {"chunk": chunk2},
    }


async def _empty_stream():
    """Stream with no on_chat_model_stream events (simulates end_session node)."""
    yield {"event": "on_chain_start", "name": "end_session", "data": {}}


async def _multi_sentence_stream():
    """Stream that builds up multiple sentences across tokens."""
    for token in ["Hello there. ", "How can ", "I help you? ", "Please let me know."]:
        chunk = MagicMock()
        chunk.content = token
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "greet"},
            "data": {"chunk": chunk},
        }


def _pushed_frames(svc: VaaniqLangGraphService) -> list:
    """Attach a frame collector to svc and return the list."""
    frames: list = []
    svc.push_frame = AsyncMock(
        side_effect=lambda f, d=FrameDirection.DOWNSTREAM: frames.append(f)
    )
    return frames


def _ctx(messages: list | None = None) -> MagicMock:
    """Build a fake Pipecat LLMContext."""
    ctx = MagicMock()
    ctx.messages = messages or []
    return ctx


# ── _split_at_sentence_boundaries ────────────────────────────────────────────

def test_split_no_boundary():
    sentences, remaining = _split_at_sentence_boundaries("Hello there")
    assert sentences == []
    assert remaining == "Hello there"


def test_split_single_sentence_no_trailing_space():
    """Sentence boundary requires whitespace AFTER the punctuation."""
    sentences, remaining = _split_at_sentence_boundaries("Hello!")
    assert sentences == []
    assert remaining == "Hello!"


def test_split_single_sentence_with_space():
    sentences, remaining = _split_at_sentence_boundaries("Hello! ")
    assert sentences == ["Hello!"]
    assert remaining == ""


def test_split_two_sentences():
    sentences, remaining = _split_at_sentence_boundaries("Hello there. How are you?")
    assert sentences == ["Hello there."]
    assert remaining == "How are you?"


def test_split_multiple_sentences():
    buf = "Hello. How are you? I'm fine."
    sentences, remaining = _split_at_sentence_boundaries(buf)
    assert sentences == ["Hello.", "How are you?"]
    assert remaining == "I'm fine."


def test_split_mid_sentence_token():
    sentences, remaining = _split_at_sentence_boundaries("The quick brown")
    assert sentences == []
    assert remaining == "The quick brown"


# ── _extract_user_text ────────────────────────────────────────────────────────

def test_extract_user_text_string_content():
    ctx = MagicMock()
    ctx.messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user",   "content": "Book me a table"},
    ]
    assert _extract_user_text(ctx) == "Book me a table"


def test_extract_user_text_block_content():
    ctx = MagicMock()
    ctx.messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " world"},
        ]},
    ]
    assert _extract_user_text(ctx) == "Hello world"


def test_extract_user_text_no_user_message():
    ctx = MagicMock()
    ctx.messages = [{"role": "system", "content": "You are helpful."}]
    assert _extract_user_text(ctx) == ""


def test_extract_user_text_returns_last_user_message():
    ctx = MagicMock()
    ctx.messages = [
        {"role": "user",      "content": "first"},
        {"role": "assistant", "content": "response"},
        {"role": "user",      "content": "second"},
    ]
    assert _extract_user_text(ctx) == "second"


# ── Internal node id detection ────────────────────────────────────────────────

def test_internal_node_ids_contains_condition_and_collect():
    svc = _make_service()
    assert "route"   in svc._internal_node_ids   # condition node
    assert "collect" in svc._internal_node_ids   # collect_data node
    assert "review"  in svc._internal_node_ids   # human_review node


def test_internal_node_ids_excludes_response_nodes():
    svc = _make_service()
    assert "greet" not in svc._internal_node_ids  # llm_response — should stream
    assert "end"   not in svc._internal_node_ids  # end_session — no LLM at all


def test_internal_node_ids_empty_config():
    svc = VaaniqLangGraphService(
        graph=_make_graph(),
        thread_id="t",
        initial_state={},
        graph_config={},
    )
    assert svc._internal_node_ids == frozenset()


# ── process_frame passthrough ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_context_frames_pass_through():
    """Non-LLMContextFrame frames must be forwarded unchanged."""
    svc = _make_service()
    frames = _pushed_frames(svc)

    frame = TextFrame(text="hello")
    await svc.process_frame(frame, FrameDirection.DOWNSTREAM)

    assert frame in frames


# ── Streaming — token delivery ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initial_turn_emits_llm_envelope_frames():
    """Turn 0 must wrap response in LLMFullResponseStart/EndFrame."""
    graph = _make_graph(stream=_token_stream("Hello!"))
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    types = [type(f) for f in frames]
    assert LLMFullResponseStartFrame in types
    assert LLMFullResponseEndFrame in types


@pytest.mark.asyncio
async def test_streaming_single_sentence_without_boundary():
    """A single token with no trailing space is flushed after stream ends."""
    graph = _make_graph(stream=_token_stream("Hello there"))
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    assert len(text_frames) == 1
    assert text_frames[0].text == "Hello there "


@pytest.mark.asyncio
async def test_streaming_sentence_boundary_flushes_early():
    """Sentence boundary mid-stream → first sentence pushed before stream ends."""
    # Two tokens that together form "Hello! How can I help?"
    graph = _make_graph(stream=_token_stream("Hello!", " How can I help?"))
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    assert len(text_frames) == 2
    assert text_frames[0].text == "Hello! "         # flushed at sentence boundary
    assert text_frames[1].text == "How can I help? "  # flushed at end of stream


@pytest.mark.asyncio
async def test_streaming_multi_sentence_across_tokens():
    """Multi-sentence stream produces one LLMTextFrame per complete sentence."""
    graph = _make_graph(stream=_multi_sentence_stream())
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    texts = [f.text for f in text_frames]
    # "Hello there." and "How can I help?" arrive via sentence boundaries
    # "Please let me know." arrives via end-of-stream flush
    assert any("Hello there." in t for t in texts)
    assert any("How can I help you?" in t for t in texts)
    assert any("Please let me know." in t for t in texts)


# ── Internal node filtering ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_node_tokens_not_streamed_to_tts():
    """Tokens from condition/routing nodes must NOT become LLMTextFrames."""
    graph = _make_graph(stream=_internal_node_stream())
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    assert len(text_frames) == 1
    assert "Hi there!" in text_frames[0].text
    # "routing decision" from the condition node must be absent
    combined = " ".join(f.text for f in text_frames)
    assert "routing decision" not in combined


@pytest.mark.asyncio
async def test_all_internal_types_filtered():
    """condition, collect_data, and human_review tokens are all filtered."""
    async def _multi_internal_stream():
        for node_type, node_id in [("condition", "route"), ("collect_data", "collect"), ("human_review", "review")]:
            chunk = MagicMock()
            chunk.content = f"internal:{node_type}"
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": node_id},
                "data": {"chunk": chunk},
            }
        # One real token
        chunk = MagicMock()
        chunk.content = "Real response."
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "greet"},
            "data": {"chunk": chunk},
        }

    graph = _make_graph(stream=_multi_internal_stream())
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    combined = " ".join(f.text for f in frames if isinstance(f, LLMTextFrame))
    assert "internal:" not in combined
    assert "Real response." in combined


# ── End-session fallback (no LLM tokens) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_end_session_farewell_pushed_from_state():
    """When no tokens stream (end_session node), agent message is read from state."""
    farewell_state = {
        "session_ended": True,
        "messages": [
            {"role": "agent", "content": "Goodbye! Have a great day."},
        ],
    }
    graph = _make_graph(stream=_empty_stream(), state_values=farewell_state)
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    assert len(text_frames) >= 1
    combined = " ".join(f.text for f in text_frames)
    assert "Goodbye!" in combined


@pytest.mark.asyncio
async def test_end_session_pushes_end_frame():
    """session_ended=True in state must cause EndFrame to be emitted."""
    graph = _make_graph(
        stream=_token_stream("Goodbye!"),
        state_values={"session_ended": True, "messages": []},
    )
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    assert any(isinstance(f, EndFrame) for f in frames)


# ── Session ended / error state ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_not_ended_when_state_is_false():
    """session_ended=False in state must NOT push an EndFrame."""
    graph = _make_graph(
        stream=_token_stream("How can I help?"),
        state_values={"session_ended": False, "messages": []},
    )
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(f, EndFrame) for f in frames)


@pytest.mark.asyncio
async def test_error_in_state_pushes_end_frame():
    """An error in the final state must end the session (push EndFrame)."""
    graph = _make_graph(
        stream=_token_stream("..."),
        state_values={"error": "LLM failed", "session_ended": False, "messages": []},
    )
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    assert any(isinstance(f, EndFrame) for f in frames)


@pytest.mark.asyncio
async def test_exception_during_stream_ends_session():
    """An exception inside astream_events must push EndFrame and not re-raise."""
    async def _boom():
        raise RuntimeError("network error")
        yield  # make it a generator

    graph = MagicMock()
    graph.astream_events = _async_iter(_boom())
    graph.aget_state = AsyncMock(return_value=_make_state_snapshot({}))
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    # Must not raise — errors are caught and session is ended gracefully
    await svc.process_frame(LLMContextFrame(context=_ctx()), FrameDirection.DOWNSTREAM)

    assert any(isinstance(f, EndFrame) for f in frames)


# ── Turn counter ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_turn_counter_starts_at_zero():
    svc = _make_service()
    assert svc._turn == 0


@pytest.mark.asyncio
async def test_turn_counter_increments_each_turn():
    graph = _make_graph()
    svc = _make_service(graph)
    svc.push_frame = AsyncMock()

    ctx0 = _ctx(messages=[])
    assert svc._turn == 0
    await svc.process_frame(LLMContextFrame(context=ctx0), FrameDirection.DOWNSTREAM)
    assert svc._turn == 1

    # Reset stream for second turn
    graph.astream_events = _async_iter(_token_stream("Got it"))
    ctx1 = _ctx(messages=[{"role": "user", "content": "Hello"}])
    await svc.process_frame(LLMContextFrame(context=ctx1), FrameDirection.DOWNSTREAM)
    assert svc._turn == 2


@pytest.mark.asyncio
async def test_turn_0_uses_initial_state():
    """Turn 0 should pass initial_state as graph input (verified by checking no user text needed)."""
    graph = _make_graph()
    svc = _make_service(graph)
    frames = _pushed_frames(svc)

    # Turn 0 with empty context — no user message needed (initial greeting)
    await svc.process_frame(LLMContextFrame(context=_ctx(messages=[])), FrameDirection.DOWNSTREAM)

    # Must have emitted at least start/end envelope
    types = [type(f) for f in frames]
    assert LLMFullResponseStartFrame in types


@pytest.mark.asyncio
async def test_turn_1_with_empty_user_text_is_skipped():
    """Turn 1+ with no user message should be a no-op (no frames pushed)."""
    graph = _make_graph()
    svc = _make_service(graph)
    svc._turn = 1  # simulate past first turn

    frames: list = []
    svc.push_frame = AsyncMock(
        side_effect=lambda f, d=FrameDirection.DOWNSTREAM: frames.append(f)
    )

    # Context has no user messages
    await svc.process_frame(LLMContextFrame(context=_ctx(messages=[])), FrameDirection.DOWNSTREAM)

    # No frames should be pushed — graph was not called
    assert frames == []


@pytest.mark.asyncio
async def test_subsequent_turn_passes_user_text():
    """Turn 1+ emits text frames from the token stream."""
    graph = _make_graph(stream=_token_stream("Sure, I can help."))
    svc = _make_service(graph)
    svc._turn = 1
    frames = _pushed_frames(svc)

    ctx = _ctx(messages=[{"role": "user", "content": "Book me a flight"}])
    await svc.process_frame(LLMContextFrame(context=ctx), FrameDirection.DOWNSTREAM)

    text_frames = [f for f in frames if isinstance(f, LLMTextFrame)]
    assert len(text_frames) == 1
    assert "Sure, I can help." in text_frames[0].text
    assert svc._turn == 2
