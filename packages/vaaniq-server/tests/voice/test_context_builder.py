"""
Unit tests for the voice context builder.

We mock the WebSocket and DB calls so no real Twilio or PostgreSQL is needed.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vaaniq.server.voice.context_builder import (
    _read_twilio_handshake,
    _resolve_provider,
    build_voice_context,
)
from vaaniq.server.voice.exceptions import (
    AgentNotConfigured,
    SessionNotFound,
    TwilioHandshakeError,
)


# ── _read_twilio_handshake ────────────────────────────────────────────────────

def _make_websocket(*messages: dict) -> AsyncMock:
    """Build a mock WebSocket that yields JSON messages in order."""
    ws = AsyncMock()
    ws.receive_text = AsyncMock(side_effect=[json.dumps(m) for m in messages])
    return ws


async def test_handshake_happy_path():
    ws = _make_websocket(
        {"event": "connected", "protocol": "Call", "version": "1.0.0"},
        {
            "event": "start",
            "streamSid": "MZ123",
            "start": {"callSid": "CA456", "accountSid": "AC789"},
        },
    )
    stream_sid, call_sid = await _read_twilio_handshake(ws)
    assert stream_sid == "MZ123"
    assert call_sid == "CA456"


async def test_handshake_missing_start_raises():
    # Only sends "connected", never "start"
    ws = AsyncMock()
    ws.receive_text = AsyncMock(
        side_effect=[json.dumps({"event": "connected"})] * 5
    )
    with pytest.raises(TwilioHandshakeError, match="'start' event"):
        await _read_twilio_handshake(ws)


async def test_handshake_websocket_closed_raises():
    ws = AsyncMock()
    ws.receive_text = AsyncMock(side_effect=Exception("connection reset"))
    with pytest.raises(TwilioHandshakeError, match="closed during handshake"):
        await _read_twilio_handshake(ws)


# ── _resolve_provider ─────────────────────────────────────────────────────────

def test_resolve_prefers_first_in_preference():
    providers = {"stt": ["assemblyai", "deepgram"]}
    result = _resolve_provider("stt", providers, ["deepgram", "assemblyai"])
    assert result == "deepgram"


def test_resolve_falls_back_to_second_preference():
    providers = {"stt": ["assemblyai"]}
    result = _resolve_provider("stt", providers, ["deepgram", "assemblyai"])
    assert result == "assemblyai"


def test_resolve_falls_back_to_default_when_none_configured():
    providers = {}  # org has no STT integration
    result = _resolve_provider("stt", providers, ["deepgram", "assemblyai"])
    assert result == "deepgram"  # first in preference list


def test_resolve_tts_prefers_cartesia():
    providers = {"tts": ["elevenlabs", "cartesia"]}
    result = _resolve_provider("tts", providers, ["cartesia", "elevenlabs", "azure"])
    assert result == "cartesia"


# ── build_voice_context (integration) ────────────────────────────────────────

def _make_session(session_id: str, org_id: str, agent_id: str) -> MagicMock:
    session = MagicMock()
    session.id = session_id
    session.org_id = org_id
    session.agent_id = agent_id
    session.user_id = "+919876543210"
    session.meta = {"call_sid": "CA999", "from": "+919876543210", "to": "+12025551234"}
    return session


def _make_agent(agent_id: str, org_id: str) -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id
    agent.org_id = org_id
    agent.language = "en-US"
    agent.voice_id = "voice-abc"
    agent.system_prompt = "You are a helpful assistant."
    agent.graph_config = {"nodes": [], "edges": [], "entry_point": "start"}
    return agent


async def test_build_voice_context_happy_path():
    ws = _make_websocket(
        {"event": "connected"},
        {"event": "start", "streamSid": "MZ123", "start": {"callSid": "CA999"}},
    )

    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1", "org-1")
    mock_org_keys = {"deepgram": "dg-key", "cartesia": "cart-key"}

    # phone_number record with no voice_config (auto-detect from org keys)
    mock_phone_number = MagicMock()
    mock_phone_number.voice_config = None

    with (
        patch("vaaniq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("vaaniq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
        patch("vaaniq.server.voice.context_builder.IntegrationRepository") as MockIntegrationRepo,
        patch("vaaniq.server.voice.context_builder.PostgresCredentialStore") as MockCredStore,
        patch("vaaniq.server.voice.context_builder.PhoneNumberRepository") as MockPhoneRepo,
        patch("vaaniq.server.voice.context_builder.platform_cache") as mock_platform_cache,
    ):
        mock_platform_cache.get_provider_config.return_value = None

        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        MockIntegrationRepo.return_value.list_by_org = AsyncMock(return_value=[])
        MockCredStore.return_value.get_org_keys = AsyncMock(return_value=mock_org_keys)
        MockPhoneRepo.return_value.get_by_number = AsyncMock(return_value=mock_phone_number)

        ctx = await build_voice_context("sess-1", ws, db=AsyncMock())

    assert ctx.session_id == "sess-1"
    assert ctx.stream_sid == "MZ123"
    assert ctx.call_sid == "CA999"
    assert ctx.stt_provider == "deepgram"
    assert ctx.tts_provider == "cartesia"
    assert ctx.agent_language == "en-US"
    assert ctx.initial_messages[0]["role"] == "system"
    assert ctx.org_keys["deepgram"] == "dg-key"


async def test_build_voice_context_session_not_found():
    ws = _make_websocket(
        {"event": "connected"},
        {"event": "start", "streamSid": "MZ123", "start": {"callSid": "CA999"}},
    )
    with patch("vaaniq.server.voice.context_builder.SessionRepository") as MockRepo:
        MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(SessionNotFound):
            await build_voice_context("missing-sess", ws, db=AsyncMock())


async def test_build_voice_context_agent_no_graph_config():
    ws = _make_websocket(
        {"event": "connected"},
        {"event": "start", "streamSid": "MZ123", "start": {"callSid": "CA999"}},
    )
    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1", "org-1")
    mock_agent.graph_config = None  # not published yet

    with (
        patch("vaaniq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("vaaniq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
    ):
        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        with pytest.raises(AgentNotConfigured):
            await build_voice_context("sess-1", ws, db=AsyncMock())
