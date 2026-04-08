"""
Post-call finalization — copies the final LangGraph state into the sessions row.

For voice calls this is called directly from the pipeline task (not via a
background task) because voice uses MemorySaver — the in-memory checkpointer
is passed in directly and read before it goes out of scope.

For the Twilio status callback fallback path (completed / failed / etc.) the
Postgres checkpointer is used as before.

What gets extracted from the LangGraph checkpoint:
  messages   → session.transcript  (full conversation history)
  tool_calls → session.tool_calls  (every tool invocation)
  summary    → session.summary     (end_session node may generate this)
  sentiment  → session.sentiment   (positive / neutral / negative)
  collected  → session.meta["collected"]  (form fields gathered during call)

If the checkpoint is missing (call dropped before any turns) the function
exits gracefully — the session stays ended with whatever fields were already set.
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.chat.checkpointer import get_checkpointer, make_thread_id
from vaaniq.server.core.database import async_session_factory
from vaaniq.server.webhooks.repository import SessionRepository

log = structlog.get_logger()


async def finalize_voice_session(
    session_id: str,
    org_id: str,
    memory_saver: Optional[Any] = None,
    event_collectors: Optional[list] = None,
) -> None:
    """
    Persist the final LangGraph state into the sessions row.

    Args:
        session_id:       The voice session UUID.
        org_id:           The org UUID.
        memory_saver:     The MemorySaver instance from the just-finished voice
                          pipeline. When provided it is used directly so no Postgres
                          checkpointer lookup is needed.  Pass None to fall back to
                          the shared Postgres checkpointer (used by the Twilio status
                          callback path).
        event_collectors: List of TurnEventCollector instances (one per turn).
                          When provided their events are bulk-inserted into
                          session_events so the Execution tab is populated.
    """
    async with async_session_factory() as db:
        await _do_finalize(session_id, org_id, db, memory_saver=memory_saver, event_collectors=event_collectors)


async def _do_finalize(
    session_id: str,
    org_id: str,
    db: AsyncSession,
    memory_saver: Optional[Any] = None,
    event_collectors: Optional[list] = None,
) -> None:
    thread_id = make_thread_id(org_id, session_id)

    # ── Load session row ──────────────────────────────────────────────────────
    session = await SessionRepository(db).get_by_id(session_id)
    if not session:
        log.warning("finalization_session_not_found", session_id=session_id)
        return

    # If the pipeline task already finalized this session (transcript present),
    # the status callback is redundant — skip the checkpointer lookup entirely.
    # This is the normal path for voice: pipeline finalizes via MemorySaver,
    # status callback arrives seconds later and finds nothing left to do.
    if session.transcript and not memory_saver:
        log.debug("finalization_already_done", session_id=session_id)
        return

    # ── Load LangGraph checkpoint ─────────────────────────────────────────────
    try:
        checkpointer = memory_saver or get_checkpointer()
        checkpoint = await checkpointer.aget({"configurable": {"thread_id": thread_id}})
    except RuntimeError:
        # Checkpointer not initialised — voice server uses MemorySaver, not Postgres.
        # If we got here the session has no transcript (pipeline never ran or crashed).
        log.debug("finalization_no_checkpointer", session_id=session_id)
        return
    except Exception:
        log.exception("finalization_checkpointer_error", session_id=session_id)
        return

    if not checkpoint:
        log.debug("finalization_no_checkpoint", session_id=session_id, thread_id=thread_id)
        return

    state: dict = checkpoint.get("channel_values", {})

    # ── Copy state fields into session ────────────────────────────────────────
    changed = False

    messages = state.get("messages")
    if messages:
        session.transcript = list(messages)
        changed = True

    tool_calls = state.get("tool_calls")
    if tool_calls:
        session.tool_calls = list(tool_calls)
        changed = True

    summary = state.get("summary")
    if summary and not session.summary:
        session.summary = summary
        changed = True

    sentiment = state.get("sentiment")
    if sentiment and not session.sentiment:
        session.sentiment = sentiment
        changed = True

    # Persist form fields collected during the call into meta
    collected = state.get("collected")
    if collected:
        meta = dict(session.meta or {})
        meta["collected"] = collected
        session.meta = meta
        changed = True

    # Stamp ended_at if not already set
    if not session.ended_at:
        session.ended_at = datetime.now(timezone.utc)
        changed = True

    # ── Persist execution events (Execution tab in Sessions UI) ──────────────
    event_count = 0
    if event_collectors:
        from vaaniq.server.chat.tracing import SessionEventRepository
        all_events = []
        for collector in event_collectors:
            all_events.extend(collector.finalize())
        if all_events:
            await SessionEventRepository(db).bulk_insert(all_events)
            event_count = len(all_events)
            changed = True

    if changed:
        await db.commit()

    log.info(
        "voice_session_finalized",
        session_id=session_id,
        has_summary=bool(summary),
        has_sentiment=bool(sentiment),
        message_count=len(messages) if messages else 0,
        event_count=event_count,
    )
