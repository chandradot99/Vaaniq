"""
Pipeline lifecycle management — build, start, run, clean up.

Entry point for each incoming Twilio WebSocket call:
  1. Build the pipeline from VoiceCallContext
  2. Create a PipelineTask with interruptions enabled
  3. Queue the initial LLMContextFrame → triggers the turn-0 greeting
  4. Run until the call ends (WebSocket close or EndFrame from session_ended)
"""

from __future__ import annotations

import asyncio
from typing import Callable

import structlog
from pipecat.frames.frames import EndFrame, LLMContextFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from vaaniq.voice.constants import (
    PIPELINE_IDLE_TIMEOUT_SECS,
    PIPELINE_SHUTDOWN_TIMEOUT_SECS,
    TWILIO_SAMPLE_RATE,
)
from vaaniq.voice.pipeline.builder import build_pipeline
from vaaniq.voice.pipeline.context import VoiceCallContext

log = structlog.get_logger()


def _make_turn_callback_factory(
    session_id: str,
    graph_config: dict,
    event_collectors: list,
) -> Callable[[int], list]:
    """
    Return a per-turn callback factory that creates a TurnEventCollector for
    each graph turn and appends it to event_collectors for later finalization.

    Imported lazily so vaaniq-voice doesn't take a hard dependency on
    vaaniq-server at import time — vaaniq-server is only available at runtime
    in the full server environment.
    """
    def get_turn_callbacks(turn: int) -> list:
        from vaaniq.server.chat.tracing import TurnEventCollector
        collector = TurnEventCollector(
            session_id=session_id,
            turn=turn,
            graph_config=graph_config,
        )
        event_collectors.append(collector)
        return [collector.as_callback_handler()]

    return get_turn_callbacks


async def _shutdown_runner(
    task: PipelineTask,
    runner_task: asyncio.Task,
    session_id: str,
) -> None:
    """
    Push a final EndFrame and wait briefly for the pipeline to flush cleanly.
    Cancels the runner task if it doesn't finish within PIPELINE_SHUTDOWN_TIMEOUT_SECS.
    """
    try:
        await task.queue_frames([EndFrame()])
        if not runner_task.done():
            await asyncio.wait_for(
                asyncio.shield(runner_task),
                timeout=PIPELINE_SHUTDOWN_TIMEOUT_SECS,
            )
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass
    finally:
        if not runner_task.done():
            runner_task.cancel()


async def _finalize_session(
    session_id: str,
    org_id: str,
    memory_saver,
    event_collectors: list,
) -> None:
    """
    Persist transcript and execution events to the database.

    asyncio.shield() ensures the DB write completes even if FastAPI cancels
    the parent WebSocket handler coroutine when the connection closes.
    """
    from vaaniq.server.voice.finalization import finalize_voice_session

    try:
        await asyncio.shield(finalize_voice_session(
            session_id=session_id,
            org_id=org_id,
            memory_saver=memory_saver,
            event_collectors=event_collectors or None,
        ))
    except asyncio.CancelledError:
        # Handler cancelled (WebSocket closed) but asyncio.shield() ensures
        # finalize_voice_session runs to completion in the background.
        log.info("voice_finalization_shielded", session_id=session_id)
    except Exception:
        log.exception("voice_finalization_error", session_id=session_id)


async def run_voice_pipeline(
    websocket,
    context: VoiceCallContext,
    checkpointer=None,
) -> None:
    """
    Entry point called by the WebSocket endpoint for each incoming call.

    Args:
        websocket:    FastAPI WebSocket object for this call.
        context:      Fully resolved VoiceCallContext (built by context_builder.py).
        checkpointer: AsyncPostgresSaver (production) or None (dev → MemorySaver).
                      Passed through to build_pipeline and returned for finalization.
    """
    log.info(
        "voice_pipeline_start",
        session_id=context.session_id,
        org_id=context.org_id,
        direction=context.direction,
        stt=context.stt_provider,
        tts=context.tts_provider,
        language=context.agent_language,
    )

    task: PipelineTask | None = None
    runner_task: asyncio.Task | None = None
    memory_saver = None
    event_collectors: list = []

    get_turn_callbacks = _make_turn_callback_factory(
        session_id=context.session_id,
        graph_config=context.graph_config,
        event_collectors=event_collectors,
    )

    try:
        pipeline, llm_context, transport, memory_saver = await build_pipeline(
            websocket, context, get_turn_callbacks=get_turn_callbacks,
            checkpointer=checkpointer,
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                # Twilio sends 8kHz mu-law; TwilioFrameSerializer converts it to
                # 8kHz linear16 PCM. Passing TWILIO_SAMPLE_RATE prevents the
                # default 16kHz assumption, which would make Deepgram receive
                # audio at double speed and return no transcriptions.
                audio_in_sample_rate=TWILIO_SAMPLE_RATE,
            ),
            # After the call ends the input transport may stay alive waiting on
            # Twilio's lingering WebSocket. A short idle timeout ensures
            # finalization runs promptly after the last speaking frame.
            idle_timeout_secs=PIPELINE_IDLE_TIMEOUT_SECS,
        )

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, websocket):
            log.info("voice_client_disconnected", session_id=context.session_id)
            await task.queue_frames([EndFrame()])

        # Queue the initial LLMContextFrame to fire turn 0 (the greeting).
        await task.queue_frames([LLMContextFrame(context=llm_context)])

        runner = PipelineRunner(handle_sigint=False)
        runner_task = asyncio.create_task(runner.run(task))
        await runner_task

    except asyncio.CancelledError:
        log.info("voice_pipeline_cancelled", session_id=context.session_id)

    except Exception as exc:
        log.exception(
            "voice_pipeline_error",
            session_id=context.session_id,
            org_id=context.org_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    finally:
        if task is not None and runner_task is not None:
            await _shutdown_runner(task, runner_task, context.session_id)

        if memory_saver is not None:
            await _finalize_session(
                session_id=context.session_id,
                org_id=context.org_id,
                memory_saver=memory_saver,
                event_collectors=event_collectors,
            )

        log.info("voice_pipeline_end", session_id=context.session_id)
