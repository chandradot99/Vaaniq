"""
VaaniqVoiceAgent — LiveKit Agent wrapper for VaaniQ's voice pipeline.

Wires together:
  VAD (Silero)  →  STT (Deepgram/Sarvam/AssemblyAI)
               →  LLM (LangGraph via LangGraphLLM adapter)
               →  TTS (Cartesia/ElevenLabs/Azure/Deepgram/Sarvam)

The agent is created once per call and attached to a LiveKit room by the
worker (worker.py). LiveKit handles VAD, turn detection, interruptions,
and audio I/O — the agent only needs to define the pipeline components.

LangGraph integration:
  - graph is compiled once at agent creation with the Postgres checkpointer
  - thread_id = session_id → multi-turn memory persists across server restarts
  - LangGraphLLM.chat() drives each user turn through the graph state machine
"""

import asyncio

import structlog
from livekit.agents import Agent, AgentSession, JobContext
from livekit.plugins import silero
from vaaniq.voice.llm import LangGraphLLM
from vaaniq.voice.pipeline.context import VoiceCallContext
from vaaniq.voice.stt import create_stt_plugin
from vaaniq.voice.tts import create_tts_plugin

log = structlog.get_logger()

# Default endpointing delays (seconds). Sarvam AI needs 70ms; Deepgram works
# well at 200ms. Turn detection="stt" is used (STT-based, not pure VAD).
_DEFAULT_MIN_ENDPOINTING_DELAY = 0.3
_SARVAM_MIN_ENDPOINTING_DELAY = 0.07


async def run_voice_agent(
    ctx: JobContext,
    context: VoiceCallContext,
    graph,
    checkpointer=None,
    on_session_ended=None,
    on_turn_events=None,
) -> None:
    """
    Run the voice agent for a single call in the given LiveKit room.

    Args:
        ctx:         LiveKit JobContext (room + participant access).
        context:     Fully resolved VoiceCallContext (STT/TTS config, org keys).
        graph:       Compiled LangGraph (from graph cache, with checkpointer baked in).
        checkpointer: The checkpointer baked into the graph (used for state reads).
    """
    await ctx.connect()

    log.info(
        "voice_agent_starting",
        session_id=context.session_id,
        stt_provider=context.stt_provider,
        stt_model=context.stt_model,
        tts_provider=context.tts_provider,
        tts_model=context.tts_model,
        language=context.agent_language,
    )

    # Build initial LangGraph state (triggers greeting on turn 0).
    initial_state = _build_initial_state(context)

    # thread_id is org-scoped to prevent cross-tenant state access.
    # Must match make_thread_id(org_id, session_id) used by finalization.
    thread_id = f"{context.org_id}:{context.session_id}"

    # AgentSession is created here so both the state-change listener and the
    # LangGraphLLM callback can reference it via closure.
    session = AgentSession()

    # ── Initial greeting trigger ──────────────────────────────────────────────
    # session.start(capture_run=True) blocks at `await run_state` until the call
    # ends — there is no sequential place to call generate_reply() after it.
    # Instead, register a one-shot listener: when the session first transitions
    # to "listening" (i.e. it's fully initialised and ready), call
    # session.generate_reply() with no user input. This triggers
    # LangGraphLLM.chat() for turn 0, which emits the greeting from graph_config
    # and advances the graph to the inbound_message interrupt so turn 1 can
    # resume with Command(resume=user_text).
    _initial_greeted = False

    @session.on("agent_state_changed")
    def _trigger_initial_greeting(ev) -> None:
        nonlocal _initial_greeted
        if not _initial_greeted and ev.new_state == "listening":
            _initial_greeted = True
            session.off("agent_state_changed", _trigger_initial_greeting)
            log.info("voice_agent_triggering_greeting", session_id=context.session_id)
            session.generate_reply()  # calls LangGraphLLM.chat() with turn=0

    # ── Wait for speech completion (event-based, no fixed sleep) ─────────────
    # These two events coordinate the session-end sequence:
    #   _should_end   — set by LangGraphLLM when session_ended=True is detected
    #   _speech_done  — set by the agent_state_changed listener when the agent
    #                   finishes speaking after _should_end is set
    _should_end = asyncio.Event()
    _speech_done = asyncio.Event()

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev) -> None:
        # Fire only when the agent STOPS speaking AND we're in the end-session path.
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            if _should_end.is_set():
                _speech_done.set()

    async def _trigger_session_end() -> None:
        """Called (via asyncio.create_task) when LangGraph sets session_ended=True.

        Sets the _should_end flag so the next 'speaking → idle/listening'
        transition on the AgentSession signals speech completion. Then waits
        for that signal before invoking the caller-supplied callback.
        """
        _should_end.set()
        try:
            # Wait for the agent to finish speaking the farewell.
            # No fixed sleep — _speech_done fires via agent_state_changed.
            await asyncio.wait_for(_speech_done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            log.warning("farewell_speaking_timeout", session_id=context.session_id)
        finally:
            session.off("agent_state_changed", _on_agent_state_changed)

        if on_session_ended:
            await on_session_ended()
        else:
            # Fallback when no caller callback provided (e.g. direct usage).
            try:
                await ctx.room.disconnect()
                log.info("voice_agent_room_disconnected", session_id=context.session_id)
            except Exception as exc:
                log.warning(
                    "voice_agent_disconnect_failed",
                    session_id=context.session_id,
                    error=str(exc),
                )

    # Instantiate the LangGraph LLM adapter.
    langgraph_llm = LangGraphLLM(
        graph=graph,
        thread_id=thread_id,
        initial_state=initial_state,
        graph_config=context.graph_config,
        on_session_ended=_trigger_session_end,
        on_turn_events=on_turn_events,
    )

    # Create STT and TTS plugins from org's configured providers.
    stt_plugin = create_stt_plugin(context)
    tts_plugin = create_tts_plugin(context)

    # VAD: Silero is the most reliable option for phone calls.
    # LiveKit handles the VAD internally when passed to Agent.
    vad = silero.VAD.load()

    # Endpointing delay: Sarvam signals faster than Deepgram.
    min_endpointing_delay = (
        _SARVAM_MIN_ENDPOINTING_DELAY
        if context.stt_provider == "sarvam"
        else _DEFAULT_MIN_ENDPOINTING_DELAY
    )

    # Build the agent. The `instructions` field sets the system context for
    # LiveKit's session management; actual conversation logic is in LangGraph.
    agent = Agent(
        instructions=(
            "You are a helpful AI voice assistant. "
            "Respond naturally and concisely to the user's spoken input."
        ),
        stt=stt_plugin,
        vad=vad,
        llm=langgraph_llm,
        tts=tts_plugin,
        allow_interruptions=True,
        min_endpointing_delay=min_endpointing_delay,
    )

    # Start the agent session and block until the call ends.
    # capture_run=True makes session.start() return a RunResult that is
    # awaitable — it resolves when the session closes (participant leaves,
    # room deleted, or agent shut down). Replaces the removed run_until_disconnected().
    log.info("voice_agent_started", session_id=context.session_id)
    await session.start(
        agent=agent,
        room=ctx.room,
        capture_run=True,
    )

    log.info("voice_agent_ended", session_id=context.session_id)


def _build_initial_state(context: VoiceCallContext) -> dict:
    """
    Build the initial LangGraph state for turn 0 (agent greeting).

    Matches the SessionState TypedDict in vaaniq-core. The graph reads this
    state at the start of the call to produce the greeting message.
    """
    return {
        "session_id": context.session_id,
        "agent_id": context.agent_id,
        "org_id": context.org_id,
        "channel": "voice",
        "user_id": context.from_number,
        "messages": context.initial_messages or [],
        "current_node": context.graph_config.get("entry_point", "start"),
        "collected": {},
        "rag_context": "",
        "crm_record": None,
        "tool_calls": [],
        "route": None,
        "transfer_to": None,
        "start_time": _utcnow(),
        "end_time": None,
        "duration_seconds": None,
        "summary": None,
        "sentiment": None,
        "action_items": [],
        "post_actions_completed": [],
        "session_ended": False,
        "transfer_initiated": False,
        "error": None,
    }


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
