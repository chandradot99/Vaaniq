"""
VoicePipelineBuilder — assembles the Pipecat pipeline for a single call.

Pipeline order:
    transport.input()
        → STT            (audio → TranscriptionFrame)
        → user_agg       (TranscriptionFrame → LLMContextFrame when user turn ends)
        → VaaniqLangGraphService  (LLMContextFrame → LLMTextFrame tokens)
        → TTS            (LLMTextFrame → AudioRawFrame)
        → assistant_agg  (accumulates agent tokens back into context)
        → transport.output()

The context (LLMContext) holds only the current turn's messages. Long-term
conversation memory lives in LangGraph's MemorySaver checkpointer — not here.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Callable, Optional

from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from vaaniq.voice.constants import TWILIO_SAMPLE_RATE
from vaaniq.voice.pipeline.context import VoiceCallContext
from vaaniq.voice.services.langgraph_service import VaaniqLangGraphService
from vaaniq.voice.services.stt.base import create_stt_service
from vaaniq.voice.services.tts.base import create_tts_service
from vaaniq.voice.services.vad import get_vad_analyzer
from vaaniq.voice.transport.base import create_transport

log = structlog.get_logger()


def _build_initial_state(context: VoiceCallContext) -> dict:
    """Construct the LangGraph SessionState snapshot for turn 0 (the greeting)."""
    return {
        "session_id": context.session_id,
        "agent_id": context.agent_id,
        "org_id": context.org_id,
        "channel": "voice",
        "user_id": context.from_number,
        "messages": [],
        "current_node": "",
        "collected": {},
        "rag_context": "",
        "crm_record": None,
        "tool_calls": [],
        "route": None,
        "transfer_to": None,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "duration_seconds": None,
        "summary": None,
        "sentiment": None,
        "action_items": [],
        "post_actions_completed": [],
        "session_ended": False,
        "transfer_initiated": False,
        "error": None,
        **context.extra_context,
    }


async def build_pipeline(
    websocket,
    context: VoiceCallContext,
    get_turn_callbacks: Optional[Callable[[int], list]] = None,
) -> tuple[Pipeline, LLMContext, object, object]:
    """
    Assemble the full Pipecat pipeline for one voice call.

    Returns:
        pipeline:      Ready-to-run Pipecat Pipeline.
        llm_context:   The LLMContext so the task runner can queue the initial
                       LLMContextFrame that triggers the turn-0 greeting.
        transport:     The FastAPIWebsocketTransport — caller registers
                       on_client_disconnected to push EndFrame on hangup.
        memory_saver:  The MemorySaver checkpointer — caller reads the final
                       state after pipeline ends and writes transcript to DB.
    """
    log.info(
        "pipeline_build_start",
        session_id=context.session_id,
        org_id=context.org_id,
        stt=context.stt_provider,
        tts=context.tts_provider,
    )

    # ── 1. Telephony transport (audio I/O) ────────────────────────────────────
    transport = create_transport(websocket, context)

    # ── 2. STT: audio → TranscriptionFrame ───────────────────────────────────
    stt = create_stt_service(
        provider=context.stt_provider,
        org_keys=context.org_keys,
        language=context.agent_language,
        model=context.stt_model,
        sample_rate=TWILIO_SAMPLE_RATE,
    )

    # ── 3. VAD + aggregators ──────────────────────────────────────────────────
    # get_vad_analyzer() returns the process-wide singleton loaded at startup.
    # First call loads the Silero model (~100ms); subsequent calls are instant.
    llm_context = LLMContext(messages=list(context.initial_messages))
    aggregator_pair = LLMContextAggregatorPair(
        llm_context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=get_vad_analyzer(),
        ),
    )

    # ── 4. LangGraph: get from cache or compile ───────────────────────────────
    # The cache owns a shared MemorySaver per agent version. Each call uses a
    # unique thread_id = "{org_id}:{session_id}", so concurrent calls to the
    # same agent don't contaminate each other's state.
    from vaaniq.graph.cache import get_or_compile

    graph, memory_saver = await get_or_compile(
        agent_id=context.agent_id,
        graph_version=context.graph_version,
        graph_config=context.graph_config,
        org_keys=context.org_keys,
    )
    thread_id = f"{context.org_id}:{context.session_id}"
    initial_state = _build_initial_state(context)

    # ── 5. LangGraph bridge (LLMContextFrame → LLMTextFrame tokens) ───────────
    langgraph_service = VaaniqLangGraphService(
        graph=graph,
        thread_id=thread_id,
        initial_state=initial_state,
        graph_config=context.graph_config,
        get_turn_callbacks=get_turn_callbacks,
    )

    # ── 6. TTS: LLMTextFrame tokens → AudioRawFrame ───────────────────────────
    tts = create_tts_service(
        provider=context.tts_provider,
        org_keys=context.org_keys,
        voice_id=context.agent_voice_id,
        model=context.tts_model,
        speed=context.tts_speed,
        language=context.agent_language,
        sample_rate=TWILIO_SAMPLE_RATE,
    )

    # ── 7. Assemble pipeline ──────────────────────────────────────────────────
    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregator_pair.user(),
        langgraph_service,
        tts,
        aggregator_pair.assistant(),
        transport.output(),
    ])

    log.info("pipeline_build_complete", session_id=context.session_id)
    return pipeline, llm_context, transport, memory_saver
