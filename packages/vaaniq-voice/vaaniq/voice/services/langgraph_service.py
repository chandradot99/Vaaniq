"""
VaaniqLangGraphService — the bridge between Pipecat and VaaniQ's LangGraph engine.

Subclasses FrameProcessor directly (not LLMService) because we don't need
Pipecat's function-calling machinery — LangGraph handles tool calling and
conversation memory internally via its own checkpointer.

Pipeline position:
    STT → LLMContextAggregatorPair.user() → VaaniqLangGraphService → TTS
                                                     ↑
                     Receives LLMContextFrame (carries user transcript)
                     Emits LLMTextFrame tokens → TTS starts streaming immediately

Turn flow:
    Turn 0  (call start, no user input yet):
        → astream_events(initial_state) → agent greeting → TTS speaks
    Turn 1+ (user spoke):
        → astream_events(Command(resume=user_text)) → runs graph → response → TTS

Streaming strategy:
    Uses astream_events() with on_chat_model_stream events to push LLMTextFrame
    per sentence as they arrive — TTS starts speaking after the first sentence
    instead of waiting for the full response (~600ms saved per turn).

    Internal LLM nodes (condition, collect_data, human_review) are filtered out
    so only agent-facing responses reach TTS. Nodes without an LLM call (e.g.
    end_session farewell) fall back to state extraction after the stream ends.
"""

import re
from typing import Callable, Optional, Union

import structlog
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = structlog.get_logger()

# Sentence boundary: split after . ! ? followed by whitespace or end of string.
# Keeps the punctuation attached to the sentence.
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')

# Node types whose LLM calls are internal (routing, review, data collection).
# Tokens from these nodes must not reach TTS.
_INTERNAL_LLM_TYPES = frozenset({"condition", "human_review", "collect_data"})


def _extract_user_text(context) -> str:
    """Return the last user message text from a Pipecat LLMContext."""
    messages = getattr(context, "messages", None) or []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                return "".join(
                    block.get("text", "")
                    for block in content
                    if block.get("type") == "text"
                )
            return str(content)
    return ""


def _extract_agent_text(state: dict) -> str:
    """Return the latest agent message from the final graph state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "agent":
            return msg.get("content", "")
    return ""


def _split_at_sentence_boundaries(buffer: str) -> tuple[list[str], str]:
    """Split buffer at sentence boundaries.

    Returns (complete_sentences, remaining_buffer).
    Sentences are flushed as soon as a sentence-ending punctuation + whitespace
    is detected in the stream — TTS can start rendering the first sentence while
    the LLM is still generating the rest.
    """
    parts = _SENTENCE_RE.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    sentences = [p.strip() for p in parts[:-1] if p.strip()]
    return sentences, parts[-1]


def _split_sentences(text: str) -> list[str]:
    """Split a complete text into sentences (used for non-streamed fallback)."""
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


class VaaniqLangGraphService(FrameProcessor):
    """
    Pipecat FrameProcessor that routes user turns through VaaniQ's LangGraph engine.
    """

    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        thread_id: str,
        initial_state: dict,
        graph_config: dict,
        get_turn_callbacks: Optional[Callable[[int], list]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._graph = graph
        self._thread_id = thread_id
        self._base_config: dict = {"configurable": {"thread_id": thread_id}}
        self._initial_state = initial_state
        self._graph_config = graph_config
        self._get_turn_callbacks = get_turn_callbacks
        self._turn: int = 0

        # Pre-compute internal node ids to filter from the token stream.
        # These nodes use LLMs for routing/review — their tokens must not reach TTS.
        self._internal_node_ids: frozenset[str] = frozenset(
            node["id"]
            for node in (graph_config.get("nodes") or [])
            if node.get("type") in _INTERNAL_LLM_TYPES
        )

    # ── Pipecat frame routing ─────────────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame):
            await self._run_graph_turn(frame.context)
        else:
            await self.push_frame(frame, direction)

    # ── Turn execution ────────────────────────────────────────────────────────

    async def _run_graph_turn(self, context) -> None:
        log.info("langgraph_turn_start", thread_id=self._thread_id, turn=self._turn)

        graph_input = self._build_graph_input(context)
        if graph_input is None:
            return

        await self.push_frame(LLMFullResponseStartFrame())
        session_ended = False

        try:
            invoke_config = self._build_invoke_config()
            token_buffer = ""
            streamed_tokens = False

            async for event in self._graph.astream_events(
                graph_input, config=invoke_config, version="v2"
            ):
                if event["event"] != "on_chat_model_stream":
                    continue

                # Filter tokens from internal routing/review nodes
                langgraph_node = event.get("metadata", {}).get("langgraph_node", "")
                if langgraph_node in self._internal_node_ids:
                    continue

                chunk = event["data"].get("chunk")
                token = getattr(chunk, "content", "") if chunk else ""
                if not token:
                    continue

                streamed_tokens = True
                token_buffer += token

                # Push complete sentences immediately so TTS starts on the first one
                sentences, token_buffer = _split_at_sentence_boundaries(token_buffer)
                for sentence in sentences:
                    await self.push_frame(LLMTextFrame(text=sentence + " "))

            # Flush any remaining text (last sentence without trailing punctuation+space)
            if token_buffer.strip():
                await self.push_frame(LLMTextFrame(text=token_buffer.strip() + " "))

            # Get final state for session_ended check and non-LLM fallback
            state_snapshot = await self._graph.aget_state(self._base_config)
            final_state = state_snapshot.values if state_snapshot else {}
            session_ended = await self._handle_stream_result(final_state, streamed_tokens)

        except Exception:
            log.exception("langgraph_turn_error", thread_id=self._thread_id, turn=self._turn)
            session_ended = True

        finally:
            self._turn += 1

        await self.push_frame(LLMFullResponseEndFrame())

        if session_ended:
            await self._end_session()

    def _build_graph_input(self, context) -> Optional[Union[dict, Command]]:
        """Return the input for graph.astream_events — initial state for turn 0, Command for turn 1+."""
        if self._turn == 0:
            return self._initial_state

        user_text = _extract_user_text(context)
        if not user_text:
            log.warning("langgraph_empty_user_text", thread_id=self._thread_id)
            return None

        log.info(
            "langgraph_user_text",
            thread_id=self._thread_id,
            turn=self._turn,
            text=user_text,
        )
        return Command(resume=user_text)

    def _build_invoke_config(self) -> dict:
        """Build the LangGraph config, injecting turn callbacks if configured.

        Callback setup is best-effort — a failure here must not prevent the graph
        from running, as that would lose the transcript for this turn.
        """
        config = dict(self._base_config)
        if not self._get_turn_callbacks:
            return config

        try:
            callbacks = self._get_turn_callbacks(self._turn)
            if callbacks:
                config = {**config, "callbacks": callbacks}
        except Exception:
            log.warning(
                "langgraph_callbacks_setup_failed",
                thread_id=self._thread_id,
                turn=self._turn,
                exc_info=True,
            )

        return config

    async def _handle_stream_result(self, final_state: dict, streamed_tokens: bool) -> bool:
        """Process final state after streaming completes. Returns True if session should end."""
        if final_state.get("error"):
            log.error(
                "langgraph_turn_error_state",
                thread_id=self._thread_id,
                turn=self._turn,
                error=final_state["error"],
            )
            return True

        # Fallback for nodes that don't call an LLM (e.g. end_session farewell message):
        # no on_chat_model_stream events fire, so push agent text from state instead.
        if not streamed_tokens:
            agent_text = _extract_agent_text(final_state)
            if agent_text:
                for sentence in _split_sentences(agent_text):
                    await self.push_frame(LLMTextFrame(text=sentence + " "))

        log.info(
            "langgraph_turn_complete",
            thread_id=self._thread_id,
            turn=self._turn,
            streamed=streamed_tokens,
        )
        return bool(final_state.get("session_ended"))

    async def _end_session(self) -> None:
        """Signal pipeline shutdown by pushing EndFrame in both directions."""
        log.info("langgraph_session_ended", thread_id=self._thread_id)
        # Downstream: TTS → output transport
        # Upstream: user_agg → STT → input transport
        # Both are required — upstream alone leaves the output transport running;
        # downstream alone leaves FastAPIWebsocketInputTransport._audio_task dangling.
        await self.push_frame(EndFrame())
        await self.push_frame(EndFrame(), FrameDirection.UPSTREAM)
