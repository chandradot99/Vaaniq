"""
Tests for post-call session finalization.

All tests mock the checkpointer and DB session — no real Postgres required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session(session_id="sess-1", org_id="org-1"):
    s = MagicMock()
    s.id = session_id
    s.org_id = org_id
    s.summary = None
    s.sentiment = None
    s.ended_at = None
    s.transcript = []
    s.tool_calls = []
    s.meta = {}
    return s


def _make_checkpoint(state: dict):
    return {"channel_values": state}


# ── finalize_voice_session ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finalization_copies_summary_and_sentiment():
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    checkpoint = _make_checkpoint({"summary": "Call went well.", "sentiment": "positive", "messages": [], "tool_calls": []})

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=checkpoint)

    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)

    db = AsyncMock()
    db.commit = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    assert session.summary == "Call went well."
    assert session.sentiment == "positive"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_finalization_copies_transcript():
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    messages = [
        {"role": "agent", "content": "Hi there!", "timestamp": "t1", "node_id": "n1"},
        {"role": "user", "content": "Hello", "timestamp": "t2", "node_id": ""},
    ]
    checkpoint = _make_checkpoint({"messages": messages})

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=checkpoint)
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    assert session.transcript == messages


@pytest.mark.asyncio
async def test_finalization_copies_collected_into_meta():
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    session.meta = {"call_sid": "CA-123"}
    checkpoint = _make_checkpoint({"collected": {"name": "Rahul", "budget": "80L"}})

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=checkpoint)
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    assert session.meta["collected"] == {"name": "Rahul", "budget": "80L"}
    assert session.meta["call_sid"] == "CA-123"   # original meta preserved


@pytest.mark.asyncio
async def test_finalization_stamps_ended_at():
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    assert session.ended_at is None
    checkpoint = _make_checkpoint({})

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=checkpoint)
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    assert session.ended_at is not None


@pytest.mark.asyncio
async def test_finalization_skips_if_no_checkpoint():
    """Checkpointer returns None (no state) → nothing to write."""
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    session.transcript = []  # no transcript — must proceed to checkpointer

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=None)
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    # Checkpointer was called but returned nothing — nothing committed
    mock_checkpointer.aget.assert_called_once()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_finalization_skips_if_already_finalized():
    """Session already has transcript (pipeline already ran) → skip quietly."""
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    session.transcript = [{"role": "agent", "content": "Hello"}]  # already set

    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    # No checkpointer access, no commit — status callback was redundant
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_finalization_graceful_if_checkpointer_not_init():
    """RuntimeError from get_checkpointer() is caught and logged as debug, not re-raised."""
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    session.transcript = []  # no transcript — must try checkpointer

    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", side_effect=RuntimeError("not init")),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        # Must not raise
        await _do_finalize("sess-1", "org-1", db)

    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_finalization_does_not_overwrite_existing_summary():
    from naaviq.server.voice.finalization import _do_finalize

    session = _make_session()
    session.summary = "Already set by end_session node."
    checkpoint = _make_checkpoint({"summary": "New summary from checkpoint."})

    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget = AsyncMock(return_value=checkpoint)
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_id = AsyncMock(return_value=session)
    db = AsyncMock()

    with (
        patch("naaviq.server.voice.finalization.get_checkpointer", return_value=mock_checkpointer),
        patch("naaviq.server.voice.finalization.SessionRepository", return_value=mock_session_repo),
    ):
        await _do_finalize("sess-1", "org-1", db)

    # Original summary should be preserved (first write wins)
    assert session.summary == "Already set by end_session node."


# ── handle_status + background task ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_status_returns_session_info_on_terminal():
    from naaviq.server.models.session import Session, SessionStatus
    from naaviq.server.webhooks.service import VoiceWebhookService

    session = MagicMock(spec=Session)
    session.id = "sess-1"
    session.org_id = "org-1"
    session.status = SessionStatus.active

    mock_session_repo = AsyncMock()
    mock_session_repo.get_by_call_sid = AsyncMock(return_value=session)

    db = AsyncMock()
    db.commit = AsyncMock()

    svc = VoiceWebhookService.__new__(VoiceWebhookService)
    svc.db = db
    svc.agent_repo = MagicMock()
    svc.session_repo = mock_session_repo

    result = await svc.handle_status("CA-123", "completed", "42")

    assert result == ("sess-1", "org-1")
    assert session.status == SessionStatus.ended
    assert session.duration_seconds == 42


@pytest.mark.asyncio
async def test_handle_status_returns_none_on_non_terminal():
    from naaviq.server.models.session import Session, SessionStatus
    from naaviq.server.webhooks.service import VoiceWebhookService

    session = MagicMock(spec=Session)
    session.id = "sess-1"
    session.org_id = "org-1"
    session.status = SessionStatus.active

    mock_session_repo = AsyncMock()
    mock_session_repo.get_by_call_sid = AsyncMock(return_value=session)

    db = AsyncMock()
    svc = VoiceWebhookService.__new__(VoiceWebhookService)
    svc.db = db
    svc.agent_repo = MagicMock()
    svc.session_repo = mock_session_repo

    result = await svc.handle_status("CA-123", "in-progress", "0")

    assert result is None
    # Status should NOT be changed for non-terminal events
    assert session.status == SessionStatus.active
