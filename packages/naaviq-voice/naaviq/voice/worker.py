"""
LiveKit Worker entrypoint for naaviq-voice-server.

This module is the entry point for the LiveKit worker process. It registers
with the LiveKit server and handles job dispatch — when a new voice call
arrives (Twilio SIP → LiveKit room), LiveKit dispatches a job to this worker.

The worker:
1. Receives a JobContext containing the room and participant info.
2. Reads the session_id from the room metadata or room name.
3. Loads the VoiceCallContext from the DB (agent config, org keys, STT/TTS).
4. Loads/compiles the agent's LangGraph from the in-process cache.
5. Calls run_voice_agent() which blocks until the call ends.

Run locally:
    uv run python -m naaviq.voice.worker --dev

Production (Fly.io):
    CMD ["uv", "run", "python", "-m", "naaviq.voice.worker"]
"""

import json
import os

# LangSmith: run its background tracing threads as daemon threads so they
# die automatically when the LiveKit worker process exits, instead of
# blocking shutdown. LANGSMITH_USE_DAEMON=true sets client._use_daemon_threads
# which is read by langsmith.Client.__init__ and passed to threading.Thread().
# Tracing still works — traces are flushed before the main thread exits.
os.environ.setdefault("LANGSMITH_USE_DAEMON", "true")

import structlog
from livekit.agents import JobContext, WorkerOptions, cli

log = structlog.get_logger()


async def entrypoint(ctx: JobContext) -> None:
    """
    LiveKit job entrypoint — called once per incoming call.

    Each call runs in its own asyncio task. The worker can handle many
    concurrent calls since LiveKit dispatches jobs independently.
    """
    # ── Step 1: Extract session_id from room metadata ─────────────────────────
    # naaviq-server sets room metadata to {"session_id": "..."} when it creates
    # the LiveKit room in response to the Twilio inbound webhook.
    # Use ctx.job.room.metadata (Room proto from the dispatched job) — this is
    # populated at dispatch time. ctx.room.metadata is only available after
    # ctx.connect() is called and must not be read here.
    metadata_raw = ctx.job.room.metadata or "{}"
    try:
        metadata = json.loads(metadata_raw)
    except json.JSONDecodeError:
        log.error("worker_invalid_room_metadata", raw=metadata_raw)
        return

    session_id = metadata.get("session_id")

    if not session_id:
        # Room was created by the SIP dispatch rule (not pre-created by us).
        # dispatchRuleIndividual names the room after the Twilio caller number:
        # e.g. "+17407576101_Eov7P7RYWUsJ" → phone = "+17407576101"
        # Look up the most recent active voice session for that phone number.
        room_name = ctx.room.name
        phone = room_name.rsplit("_", 1)[0] if "_" in room_name else room_name
        if phone:
            session_id = await _find_session_by_phone(phone)
            if session_id:
                log.info("worker_session_resolved_by_phone",
                         phone=phone, session_id=session_id, room=room_name)
            else:
                log.error("worker_session_not_found_by_phone",
                          phone=phone, room=room_name)
                return
        else:
            log.error("worker_missing_session_id", room=room_name)
            return

    log.info("worker_job_received", session_id=session_id, room=ctx.room.name)

    # ── Step 2: Build VoiceCallContext from DB ────────────────────────────────
    try:
        context = await _load_context(session_id)
    except Exception as exc:
        log.exception("worker_context_load_failed", session_id=session_id, error=str(exc))
        return

    # ── Step 3: Load/compile LangGraph from cache ─────────────────────────────
    try:
        graph, checkpointer = await _load_graph(context)
    except Exception as exc:
        log.exception("worker_graph_load_failed", session_id=session_id, error=str(exc))
        return

    # ── Step 4: Run agent until call ends ─────────────────────────────────────
    # _event_collectors accumulates one TurnEventCollector per user turn.
    # The on_turn_events callback is sync (called from inside _run()) and
    # populates this list as each turn completes during the call.
    _event_collectors: list = []

    def _on_turn_events(turn: int, raw_events: list) -> None:
        from naaviq.server.chat.tracing import TurnEventCollector

        collector = TurnEventCollector(
            session_id=session_id,
            turn=turn,
            graph_config=context.graph_config,
        )
        for event in raw_events:
            collector.ingest(event)
        collector.finalize()
        _event_collectors.append(collector)

    # Build a session-ended callback that finalizes the session BEFORE
    # disconnecting the LiveKit room. Finalization must happen while the
    # entrypoint is still running — if it happens after the room disconnects,
    # LiveKit cancels the entrypoint task ("entrypoint did not exit in time")
    # before the DB write completes.
    async def _on_session_ended() -> None:
        # agent.py has already waited for the farewell speech to finish
        # (via agent_state_changed event) before calling this callback.
        # Finalize while the room is still open to avoid the LiveKit
        # "entrypoint did not exit in time" cancellation race.
        try:
            await _finalize_session(session_id, context.org_id, checkpointer, context,
                                    event_collectors=_event_collectors)
        except Exception:
            log.exception("worker_pre_finalize_failed", session_id=session_id)

        # Delete the LiveKit room — this disconnects ALL participants including
        # the browser frontend (which receives a `disconnected` event with
        # reason ROOM_DELETED). Just calling ctx.room.disconnect() only removes
        # the agent; the room stays open and the frontend stays connected.
        try:
            await _delete_livekit_room(ctx.room.name)
            log.info("worker_room_deleted", session_id=session_id, room=ctx.room.name)
        except Exception as exc:
            error_str = str(exc)
            # 404 = room already deleted (safety-net path ran after on_session_ended).
            # Only warn for unexpected errors; 404 is expected and silent.
            if "not_found" not in error_str and "does not exist" not in error_str:
                log.warning("worker_room_delete_failed", session_id=session_id, error=error_str)
                # Fall back to agent-only disconnect so session.start() unblocks.
                try:
                    await ctx.room.disconnect()
                except Exception:
                    pass

    try:
        from naaviq.voice.agent import run_voice_agent
        await run_voice_agent(
            ctx, context, graph, checkpointer,
            on_session_ended=_on_session_ended,
            on_turn_events=_on_turn_events,
        )
    except Exception as exc:
        log.exception("worker_agent_error", session_id=session_id, error=str(exc))

    # ── Step 5: Safety-net finalization ───────────────────────────────────────
    # If _on_session_ended already ran (normal path), finalize_voice_session
    # will detect session.transcript is set and exit immediately (no-op).
    # This only does real work if the call dropped before session_ended was set
    # (e.g. user hung up without going through the farewell node).
    try:
        await _finalize_session(session_id, context.org_id, checkpointer, context,
                                event_collectors=_event_collectors)
    except Exception:
        log.exception("worker_finalize_failed", session_id=session_id)


async def _load_context(session_id: str):
    """
    Load VoiceCallContext from the DB.

    Also ensures the platform_cache is populated — the worker is a separate
    process from the FastAPI server, so the in-memory cache starts empty.
    We load it here (once, on first call) using the same DB session.
    """
    from naaviq.server.admin import platform_cache
    from naaviq.server.core.database import async_session_factory
    from naaviq.server.voice.context_builder import build_voice_context

    async with async_session_factory() as db:
        if not platform_cache._cache:
            await platform_cache.reload(db)
            log.info("worker_platform_cache_loaded", providers=list(platform_cache._cache.keys()))
        return await build_voice_context(session_id=session_id, db=db)


async def _load_graph(context):
    """Load or compile the LangGraph for this agent."""
    from naaviq.graph.cache import get_or_compile
    from naaviq.server.chat.checkpointer import get_checkpointer

    try:
        checkpointer = get_checkpointer()
    except RuntimeError:
        checkpointer = None  # dev without Postgres — MemorySaver fallback

    return await get_or_compile(
        agent_id=context.agent_id,
        graph_version=context.graph_version,
        graph_config=context.graph_config,
        org_keys=context.org_keys,
        checkpointer=checkpointer,
    )


async def _delete_livekit_room(room_name: str) -> None:
    """
    Delete the LiveKit room, disconnecting all participants including the browser.

    ctx.room.disconnect() only removes the agent participant — the room stays
    open and the browser frontend stays connected. Deleting the room via the
    LiveKit API sends a ROOM_DELETED disconnect reason to all participants,
    which the frontend LiveKit SDK surfaces as a `disconnected` event so the
    UI can close the call cleanly.

    Credentials are read from LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
    env vars (same ones the worker uses to register with LiveKit).
    """
    import os

    from livekit.api import DeleteRoomRequest, LiveKitAPI

    url = os.environ.get("LIVEKIT_URL", "")
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

    if not (url and api_key and api_secret):
        raise RuntimeError("LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set")

    async with LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret) as lk:
        await lk.room.delete_room(DeleteRoomRequest(room=room_name))


async def _finalize_session(
    session_id: str,
    org_id: str,
    checkpointer,
    context,
    event_collectors: list | None = None,
) -> None:
    """
    Persist the final session state to the DB after the call ends.

    checkpointer is the effective checkpointer baked into the compiled graph
    (MemorySaver in dev, AsyncPostgresSaver in production). It is passed directly
    so finalization can read the final state without a separate DB lookup.

    event_collectors holds one TurnEventCollector per user turn — passed to
    finalize_voice_session so execution events are bulk-inserted into
    session_events (populates the Executions tab in the Sessions UI).

    Note: this is called both from _on_session_ended (before room disconnect,
    normal path) and as a safety net after run_voice_agent returns (handles
    calls that drop without going through the end_session node). The second call
    is a no-op when transcript is already set.
    """
    from naaviq.server.voice.finalization import finalize_voice_session

    await finalize_voice_session(
        session_id,
        org_id,
        memory_saver=checkpointer,
        event_collectors=event_collectors or [],
    )
    log.info("worker_session_finalized", session_id=session_id)


async def _find_session_by_phone(phone: str) -> str | None:
    """
    Find the most recent active voice session for a given phone number.

    Used as a fallback when room metadata is empty — this happens when
    LiveKit's SIP dispatch rule creates the room (naming it after the
    Twilio caller number) rather than using our pre-created room.

    Searches both:
      - inbound sessions:  user_id = phone (caller's number is the user)
      - outbound sessions: meta->>'from' = phone (org's Twilio number is the caller)

    Filters to active sessions created within the last 5 minutes.
    Returns the most recent match.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_, select
    from naaviq.server.core.database import async_session_factory
    from naaviq.server.models.session import Session, SessionStatus

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    async with async_session_factory() as db:
        stmt = (
            select(Session.id)
            .where(
                Session.channel == "voice",
                Session.status == SessionStatus.active,
                Session.created_at >= cutoff,
                or_(
                    Session.user_id == phone,
                    Session.meta["from"].astext == phone,
                ),
            )
            .order_by(Session.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return str(row) if row else None


if __name__ == "__main__":
    # Load .env from the workspace root.
    # Uses find_workspace_root() — walks up to the directory that has
    # pyproject.toml + packages/, so no fragile parent-index counting.
    from dotenv import load_dotenv
    from naaviq.server.core.env import ENV_FILE
    load_dotenv(ENV_FILE)

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="naaviq-voice",  # must match CreateAgentDispatchRequest(agent_name=...)
            # LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET are read from env.
        )
    )
