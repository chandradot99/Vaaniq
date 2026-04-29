"""
Unit tests for the TTS provider factory (LiveKit plugins).

No real API calls — plugins are instantiated but not connected.
"""

import pytest

from naaviq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from naaviq.voice.pipeline.context import VoiceCallContext
from naaviq.voice.tts import create_tts_plugin


def _ctx(**kwargs) -> VoiceCallContext:
    defaults = dict(
        session_id="sess-1",
        org_id="org-1",
        agent_id="agent-1",
        agent_language="en-US",
        graph_config={},
        graph_version=1,
        initial_messages=[],
        org_keys={},
    )
    defaults.update(kwargs)
    return VoiceCallContext(**defaults)


# ── Cartesia ──────────────────────────────────────────────────────────────────

def test_cartesia_tts_created():
    from livekit.plugins.cartesia import TTS

    ctx = _ctx(tts_provider="cartesia", org_keys={"cartesia": "cart-key-xyz"})
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_cartesia_with_voice_id_and_model():
    from livekit.plugins.cartesia import TTS

    ctx = _ctx(
        tts_provider="cartesia",
        agent_voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
        tts_model="sonic-2",
        org_keys={"cartesia": "cart-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_cartesia_missing_key_raises():
    ctx = _ctx(tts_provider="cartesia", org_keys={})
    with pytest.raises(MissingAPIKeyError) as exc_info:
        create_tts_plugin(ctx)
    assert exc_info.value.provider == "cartesia"


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def test_elevenlabs_tts_created():
    from livekit.plugins.elevenlabs import TTS

    ctx = _ctx(tts_provider="elevenlabs", org_keys={"elevenlabs": "el-key-abc"})
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_elevenlabs_with_speed():
    from livekit.plugins.elevenlabs import TTS

    ctx = _ctx(
        tts_provider="elevenlabs",
        tts_speed=1.2,
        org_keys={"elevenlabs": "el-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_elevenlabs_missing_key_raises():
    ctx = _ctx(tts_provider="elevenlabs", org_keys={})
    with pytest.raises(MissingAPIKeyError):
        create_tts_plugin(ctx)


# ── OpenAI TTS ────────────────────────────────────────────────────────────────

def test_openai_tts_created():
    from livekit.plugins.openai import TTS

    ctx = _ctx(tts_provider="openai", org_keys={"openai": "sk-test-key"})
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_openai_tts_custom_model():
    from livekit.plugins.openai import TTS

    ctx = _ctx(
        tts_provider="openai",
        tts_model="tts-1-hd",
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_openai_tts_valid_voice():
    from livekit.plugins.openai import TTS

    ctx = _ctx(
        tts_provider="openai",
        agent_voice_id="nova",
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_openai_tts_invalid_voice_falls_back():
    """Unknown voice_id should fall back to 'alloy' without raising."""
    from livekit.plugins.openai import TTS

    ctx = _ctx(
        tts_provider="openai",
        agent_voice_id="nonexistent-voice",
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_openai_tts_with_speed():
    from livekit.plugins.openai import TTS

    ctx = _ctx(
        tts_provider="openai",
        tts_speed=1.25,
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_openai_tts_missing_key_raises():
    ctx = _ctx(tts_provider="openai", org_keys={})
    with pytest.raises(MissingAPIKeyError) as exc_info:
        create_tts_plugin(ctx)
    assert exc_info.value.provider == "openai"


# ── Sarvam AI ─────────────────────────────────────────────────────────────────

def test_sarvam_tts_created():
    from naaviq.voice.tts.sarvam import SarvamTTS

    ctx = _ctx(
        tts_provider="sarvam",
        agent_language="hi-IN",
        org_keys={"sarvam": "sarvam-key"},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, SarvamTTS)


def test_sarvam_missing_key_raises():
    ctx = _ctx(tts_provider="sarvam", org_keys={})
    with pytest.raises(MissingAPIKeyError):
        create_tts_plugin(ctx)


# ── Key as dict ───────────────────────────────────────────────────────────────

def test_key_as_dict_with_api_key_field():
    from livekit.plugins.cartesia import TTS

    ctx = _ctx(
        tts_provider="cartesia",
        org_keys={"cartesia": {"api_key": "nested-cart-key"}},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


# ── Unknown provider ──────────────────────────────────────────────────────────

def test_unknown_provider_raises():
    ctx = _ctx(tts_provider="google", org_keys={"google": "key"})
    with pytest.raises(ProviderNotFoundError) as exc_info:
        create_tts_plugin(ctx)
    assert exc_info.value.provider == "google"
    assert exc_info.value.category == "tts"
