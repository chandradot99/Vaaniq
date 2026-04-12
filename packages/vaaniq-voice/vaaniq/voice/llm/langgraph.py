"""
LangGraphLLM — LiveKit LLM adapter for VaaniQ's LangGraph engine.

Bridges LiveKit's Agent model (which expects an LLM that takes a chat context
and returns a response stream) with LangGraph's stateful graph execution model.

Turn flow:
    Turn 0  (call start, no user input yet):
        Greeting is emitted directly from the start node's config (no LLM call).
        The graph is still advanced to the inbound_message interrupt so turn 1
        can resume with Command(resume=user_text).
    Turn N  (user spoke):
        → astream_events(Command(resume=user_text)) → graph resumes → response

Streaming:
    Uses astream_events(version="v2") to receive on_chat_model_stream events
    and push ChatChunk objects back to LiveKit's pipeline — TTS starts after
    the first token rather than waiting for the full response.

Internal nodes:
    Nodes of type condition, collect_data, human_review use LLMs for routing
    or data extraction — their tokens must NOT reach TTS. These are filtered
    out by node_id (computed once at construction from graph_config).

Session ending:
    When any node sets session_ended=True in the graph state, the on_session_ended
    callback is scheduled via asyncio.create_task. The callback (injected by
    agent.py) disconnects the LiveKit room so the call ends gracefully.
"""

import asyncio
import uuid
from typing import Callable, Coroutine, Optional

import structlog
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions, llm

log = structlog.get_logger()

# Node types whose LLM output is internal — must not be spoken to the user.
_INTERNAL_NODE_TYPES = frozenset({"condition", "human_review", "collect_data"})


def _extract_start_greeting(graph_config: dict) -> str:
    """Extract the greeting text from the graph's start node config."""
    entry_point = graph_config.get("entry_point", "start")
    for node in graph_config.get("nodes", []):
        if node.get("id") == entry_point and node.get("type") == "start":
            return node.get("config", {}).get("greeting", "")
    return ""


def _extract_user_text(chat_ctx: llm.ChatContext) -> str:
    """Return the last user message text from a LiveKit ChatContext."""
    for item in reversed(chat_ctx.items):
        if item.role == "user":
            return item.text_content or ""
    return ""


def _extract_agent_text(state: dict) -> str:
    """Return the latest agent message from the final graph state (fallback)."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "agent":
            return msg.get("content", "")
    return ""


def _extract_interrupt_text(state_snapshot) -> str:
    """Return speakable text from an active interrupt (collect_data question)."""
    if not state_snapshot:
        return ""
    for task in state_snapshot.tasks or []:
        for ivr in task.interrupts or []:
            value = getattr(ivr, "value", None) or {}
            if isinstance(value, dict) and "content" in value:
                return str(value["content"])
    return ""


class LangGraphLLM(llm.LLM):
    """
    LiveKit LLM implementation backed by a compiled LangGraph.

    One instance is created per call — holds the graph, thread_id (session_id),
    initial_state (for the greeting turn), and turn counter.
    """

    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        thread_id: str,
        initial_state: dict,
        graph_config: dict,
        on_session_ended: Optional[Callable[[], Coroutine]] = None,
        on_turn_events: Optional[Callable[[int, list], None]] = None,
    ) -> None:
        super().__init__()
        self._graph = graph
        self._thread_id = thread_id
        self._initial_state = initial_state
        self._turn: int = 0
        self._on_session_ended = on_session_ended
        # Called after each user turn (turn >= 1) with (turn_number, raw_events).
        # The caller (worker.py) creates TurnEventCollector instances from these
        # events without needing vaaniq-server imported inside vaaniq-voice.
        self._on_turn_events = on_turn_events

        # Extract greeting from the start node — emitted directly on turn 0
        # since the start node doesn't use LLM streaming.
        self._greeting: str = _extract_start_greeting(graph_config)

        # Pre-compute internal node IDs to filter from the token stream.
        self._internal_node_ids: frozenset[str] = frozenset(
            node["id"]
            for node in (graph_config.get("nodes") or [])
            if node.get("type") in _INTERNAL_NODE_TYPES
        )

    @property
    def model(self) -> str:
        return "langgraph"

    @property
    def provider(self) -> str:
        return "vaaniq"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: Optional[list] = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        **kwargs,
    ) -> "LangGraphLLMStream":
        turn = self._turn
        self._turn += 1
        return LangGraphLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            graph=self._graph,
            thread_id=self._thread_id,
            initial_state=self._initial_state,
            internal_node_ids=self._internal_node_ids,
            turn=turn,
            greeting=self._greeting,
            on_session_ended=self._on_session_ended,
            on_turn_events=self._on_turn_events,
        )


class LangGraphLLMStream(llm.LLMStream):
    """
    Async stream that runs one LangGraph turn and emits ChatChunk objects.

    LiveKit reads from this stream and feeds text to TTS as chunks arrive,
    so TTS can start speaking the first sentence while the LLM is still
    generating the rest.
    """

    def __init__(
        self,
        llm_instance: LangGraphLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list,
        conn_options: APIConnectOptions,
        graph: CompiledStateGraph,
        thread_id: str,
        initial_state: dict,
        internal_node_ids: frozenset,
        turn: int,
        greeting: str = "",
        on_session_ended: Optional[Callable[[], Coroutine]] = None,
        on_turn_events: Optional[Callable[[int, list], None]] = None,
    ) -> None:
        super().__init__(llm_instance, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._graph = graph
        self._thread_id = thread_id
        self._initial_state = initial_state
        self._internal_node_ids = internal_node_ids
        self._turn = turn
        self._greeting = greeting
        self._on_session_ended = on_session_ended
        self._on_turn_events = on_turn_events

    async def _run(self) -> None:
        config = {"configurable": {"thread_id": self._thread_id}}
        chunk_id = str(uuid.uuid4())

        # ── Turn 0: greeting ──────────────────────────────────────────────────
        if self._turn == 0:
            log.info("langgraph_turn_start", thread_id=self._thread_id, turn=0, type="greeting")

            # Emit the greeting directly from the start node config.
            # The start node doesn't call an LLM, so astream_events produces no
            # on_chat_model_stream events — emit from config instead of waiting.
            if self._greeting:
                self._event_ch.send_nowait(
                    llm.ChatChunk(
                        id=chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=self._greeting),
                    )
                )

            # Still advance the graph through start → inbound_message so that
            # turn 1 can resume from the interrupt with Command(resume=user_text).
            try:
                async for _event in self._graph.astream_events(
                    self._initial_state, config, version="v2"
                ):
                    pass  # consume events to advance state; no token streaming needed
            except Exception as exc:
                log.exception(
                    "langgraph_greeting_graph_error",
                    thread_id=self._thread_id,
                    error=str(exc),
                )

            log.info(
                "langgraph_turn_complete",
                thread_id=self._thread_id,
                turn=0,
                streamed=bool(self._greeting),
            )
            return

        # ── Turn N: user spoke ────────────────────────────────────────────────
        user_text = _extract_user_text(self._chat_ctx)
        if not user_text:
            log.warning("langgraph_empty_user_text", thread_id=self._thread_id, turn=self._turn)
            return

        graph_input = Command(resume=user_text)
        log.info(
            "langgraph_turn_start",
            thread_id=self._thread_id,
            turn=self._turn,
            user_text_preview=user_text[:80],
        )

        streamed_any = False
        final_state: Optional[dict] = None
        session_ended = False
        raw_events: list = []  # collected for execution tracing

        try:
            async for event in self._graph.astream_events(graph_input, config, version="v2"):
                raw_events.append(event)
                event_type = event.get("event")

                if event_type == "on_chain_end":
                    # Capture agent message for the non-streaming text fallback.
                    # session_ended is detected via aget_state() after the loop —
                    # on_chain_end output format is unreliable for state flags.
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "messages" in output:
                        final_state = output

                if event_type != "on_chat_model_stream":
                    continue

                # Filter internal-node tokens (routing, review, collect_data).
                metadata = event.get("metadata", {})
                node_id = metadata.get("langgraph_node", "")
                if node_id in self._internal_node_ids:
                    continue

                chunk = event.get("data", {}).get("chunk")
                if not chunk:
                    continue

                content = getattr(chunk, "content", "") or ""
                if not content:
                    continue

                self._event_ch.send_nowait(
                    llm.ChatChunk(
                        id=chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=content),
                    )
                )
                streamed_any = True

        except Exception as exc:
            log.exception(
                "langgraph_turn_error",
                thread_id=self._thread_id,
                turn=self._turn,
                error=str(exc),
            )
            raise

        # Always read the final state after all events are consumed.
        # session_ended detection via on_chain_end events is unreliable — when
        # an llm_response node runs before end_session, streaming tokens make
        # streamed_any=True, so the graph-level on_chain_end may not include
        # session_ended in the format we expect. aget_state() is the only
        # reliable source of truth regardless of whether streaming happened.
        # For non-streaming turns (end_session farewell, collect_data re-ask),
        # also extract the text to speak from the interrupt or agent message.
        try:
            state_snapshot = await self._graph.aget_state(config)
            if state_snapshot and state_snapshot.values.get("session_ended"):
                session_ended = True
            if not streamed_any:
                text = _extract_interrupt_text(state_snapshot) or _extract_agent_text(final_state or {})
                if text:
                    self._event_ch.send_nowait(
                        llm.ChatChunk(
                            id=chunk_id,
                            delta=llm.ChoiceDelta(role="assistant", content=text),
                        )
                    )
        except Exception:
            log.exception("langgraph_fallback_state_read_failed", thread_id=self._thread_id)

        # Fire execution tracing callback so the worker can build TurnEventCollector
        # rows without importing vaaniq-server inside vaaniq-voice.
        if self._on_turn_events and raw_events:
            try:
                self._on_turn_events(self._turn, raw_events)
            except Exception:
                log.exception("langgraph_turn_events_callback_failed", thread_id=self._thread_id)

        # Signal session end — graph set session_ended=True (e.g. end_session node).
        # Use create_task so TTS has time to finish speaking before the room closes.
        if session_ended and self._on_session_ended:
            log.info("langgraph_session_ended_detected", thread_id=self._thread_id)
            asyncio.create_task(self._on_session_ended())

        log.info(
            "langgraph_turn_complete",
            thread_id=self._thread_id,
            turn=self._turn,
            streamed=streamed_any,
            session_ended=session_ended,
        )
