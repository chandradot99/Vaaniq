"""
Unit tests for the TTS provider factory (LiveKit plugins).

No real API calls — plugins are instantiated but not connected.
"""

import pytest
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.pipeline.context import VoiceCallContext
from vaaniq.voice.tts import create_tts_plugin


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


# ── Azure ─────────────────────────────────────────────────────────────────────

def test_azure_tts_created():
    from livekit.plugins.azure import TTS

    ctx = _ctx(
        tts_provider="azure",
        agent_language="hi-IN",
        org_keys={"azure": {"api_key": "az-key", "region": "eastus"}},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_azure_tts_string_key():
    from livekit.plugins.azure import TTS

    ctx = _ctx(
        tts_provider="azure",
        org_keys={"azure": {"api_key": "az-key", "region": "eastus"}},
    )
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


def test_azure_missing_key_raises():
    ctx = _ctx(tts_provider="azure", org_keys={})
    with pytest.raises(MissingAPIKeyError):
        create_tts_plugin(ctx)


def test_azure_default_hindi_voice():
    from livekit.plugins.azure import TTS
    from vaaniq.voice.tts import _azure_default_voice

    assert _azure_default_voice("hi-IN") == "hi-IN-SwaraNeural"
    assert _azure_default_voice("ta-IN") == "ta-IN-PallaviNeural"
    assert _azure_default_voice("en-US") == "en-US-AriaNeural"


# ── Deepgram TTS ──────────────────────────────────────────────────────────────

def test_deepgram_tts_created():
    from livekit.plugins.deepgram import TTS

    ctx = _ctx(tts_provider="deepgram", org_keys={"deepgram": "dg-key"})
    plugin = create_tts_plugin(ctx)
    assert isinstance(plugin, TTS)


# ── Sarvam AI ─────────────────────────────────────────────────────────────────

def test_sarvam_tts_created():
    from vaaniq.voice.tts.sarvam import SarvamTTS

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
    ctx = _ctx(tts_provider="openai", org_keys={"openai": "key"})
    with pytest.raises(ProviderNotFoundError) as exc_info:
        create_tts_plugin(ctx)
    assert exc_info.value.provider == "openai"
    assert exc_info.value.category == "tts"
