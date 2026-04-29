"""
Unit tests for the voice context builder.

DB calls are mocked — no real PostgreSQL needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from naaviq.server.voice.context_builder import (
    _resolve_provider,
    build_voice_context,
)
from naaviq.server.voice.exceptions import (
    AgentNotConfigured,
    SessionNotFound,
)

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
    result = _resolve_provider("stt", {}, ["deepgram", "assemblyai"])
    assert result == "deepgram"


def test_resolve_tts_prefers_cartesia():
    providers = {"tts": ["elevenlabs", "cartesia"]}
    result = _resolve_provider("tts", providers, ["cartesia", "elevenlabs", "azure"])
    assert result == "cartesia"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(session_id: str, org_id: str, agent_id: str) -> MagicMock:
    session = MagicMock()
    session.id = session_id
    session.org_id = org_id
    session.agent_id = agent_id
    session.user_id = "+919876543210"
    session.meta = {
        "call_sid": "CA999",
        "from": "+919876543210",
        "to": "+12025551234",
        "direction": "inbound",
    }
    return session


def _make_agent(agent_id: str) -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id
    agent.language = "en-US"
    agent.voice_id = "voice-abc"
    agent.system_prompt = "You are a helpful assistant."
    agent.graph_config = {"nodes": [], "edges": [], "entry_point": "start"}
    agent.graph_version = 1
    return agent


# ── build_voice_context ───────────────────────────────────────────────────────

async def test_build_voice_context_happy_path():
    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1")
    mock_phone = MagicMock()
    mock_phone.voice_config = None

    with (
        patch("naaviq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("naaviq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
        patch("naaviq.server.voice.context_builder.IntegrationRepository") as MockIntegrationRepo,
        patch("naaviq.server.voice.context_builder.PostgresCredentialStore") as MockCredStore,
        patch("naaviq.server.voice.context_builder.PhoneNumberRepository") as MockPhoneRepo,
        patch("naaviq.server.voice.context_builder.platform_cache") as mock_platform_cache,
    ):
        mock_platform_cache.get_provider_config.return_value = None
        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        MockIntegrationRepo.return_value.list_by_org = AsyncMock(return_value=[])
        MockCredStore.return_value.get_org_keys = AsyncMock(
            return_value={"deepgram": "dg-key", "cartesia": "cart-key"}
        )
        MockPhoneRepo.return_value.get_by_number = AsyncMock(return_value=mock_phone)

        ctx = await build_voice_context("sess-1", db=AsyncMock())

    assert ctx.session_id == "sess-1"
    assert ctx.call_sid == "CA999"
    assert ctx.from_number == "+919876543210"
    assert ctx.to_number == "+12025551234"
    assert ctx.stt_provider == "deepgram"
    assert ctx.tts_provider == "cartesia"
    assert ctx.agent_language == "en-US"
    assert ctx.initial_messages[0]["role"] == "system"
    assert ctx.org_keys["deepgram"] == "dg-key"


async def test_build_voice_context_session_not_found():
    with patch("naaviq.server.voice.context_builder.SessionRepository") as MockRepo:
        MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(SessionNotFound):
            await build_voice_context("missing-sess", db=AsyncMock())


async def test_build_voice_context_agent_no_graph_config():
    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1")
    mock_agent.graph_config = None  # agent not published yet

    with (
        patch("naaviq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("naaviq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
    ):
        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        with pytest.raises(AgentNotConfigured):
            await build_voice_context("sess-1", db=AsyncMock())


async def test_build_voice_context_voice_config_overrides_defaults():
    """phone_number.voice_config takes precedence over auto-detected providers."""
    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1")
    mock_phone = MagicMock()
    mock_phone.voice_config = {
        "stt_provider": "sarvam",
        "tts_provider": "elevenlabs",
        "language": "hi-IN",
        "tts_voice_id": "voice-xyz",
    }

    with (
        patch("naaviq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("naaviq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
        patch("naaviq.server.voice.context_builder.IntegrationRepository") as MockIntegrationRepo,
        patch("naaviq.server.voice.context_builder.PostgresCredentialStore") as MockCredStore,
        patch("naaviq.server.voice.context_builder.PhoneNumberRepository") as MockPhoneRepo,
        patch("naaviq.server.voice.context_builder.platform_cache") as mock_platform_cache,
    ):
        mock_platform_cache.get_provider_config.return_value = None
        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        MockIntegrationRepo.return_value.list_by_org = AsyncMock(return_value=[])
        MockCredStore.return_value.get_org_keys = AsyncMock(return_value={})
        MockPhoneRepo.return_value.get_by_number = AsyncMock(return_value=mock_phone)

        ctx = await build_voice_context("sess-1", db=AsyncMock())

    assert ctx.stt_provider == "sarvam"
    assert ctx.tts_provider == "elevenlabs"
    assert ctx.agent_language == "hi-IN"
    assert ctx.agent_voice_id == "voice-xyz"


async def test_build_voice_context_platform_fallback_keys():
    """Platform keys are used when org has no BYOK integrations."""
    mock_session = _make_session("sess-1", "org-1", "agent-1")
    mock_agent = _make_agent("agent-1")
    mock_phone = MagicMock()
    mock_phone.voice_config = None

    with (
        patch("naaviq.server.voice.context_builder.SessionRepository") as MockSessionRepo,
        patch("naaviq.server.voice.context_builder.AgentRepository") as MockAgentRepo,
        patch("naaviq.server.voice.context_builder.IntegrationRepository") as MockIntegrationRepo,
        patch("naaviq.server.voice.context_builder.PostgresCredentialStore") as MockCredStore,
        patch("naaviq.server.voice.context_builder.PhoneNumberRepository") as MockPhoneRepo,
        patch("naaviq.server.voice.context_builder.platform_cache") as mock_platform_cache,
    ):
        # Platform has Deepgram + Cartesia keys configured
        def platform_config(provider):
            if provider == "deepgram":
                return {"api_key": "platform-dg-key"}
            if provider == "cartesia":
                return {"api_key": "platform-cart-key"}
            return None

        mock_platform_cache.get_provider_config.side_effect = platform_config
        MockSessionRepo.return_value.get_by_id = AsyncMock(return_value=mock_session)
        MockAgentRepo.return_value.get_by_id = AsyncMock(return_value=mock_agent)
        MockIntegrationRepo.return_value.list_by_org = AsyncMock(return_value=[])
        MockCredStore.return_value.get_org_keys = AsyncMock(return_value={})
        MockPhoneRepo.return_value.get_by_number = AsyncMock(return_value=mock_phone)

        ctx = await build_voice_context("sess-1", db=AsyncMock())

    assert ctx.org_keys.get("deepgram") == "platform-dg-key"
    assert ctx.org_keys.get("cartesia") == "platform-cart-key"
