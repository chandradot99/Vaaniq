"""
Unit tests for the STT provider factory (LiveKit plugins).

No real API calls — plugins are instantiated but not connected.
"""

import pytest
from naaviq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from naaviq.voice.pipeline.context import VoiceCallContext
from naaviq.voice.stt import create_stt_plugin


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


# ── Deepgram ──────────────────────────────────────────────────────────────────

def test_deepgram_stt_created():
    from livekit.plugins.deepgram import STT

    ctx = _ctx(stt_provider="deepgram", org_keys={"deepgram": "dg-key-123"})
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


def test_deepgram_stt_custom_model():
    from livekit.plugins.deepgram import STT

    ctx = _ctx(
        stt_provider="deepgram",
        stt_model="nova-2",
        org_keys={"deepgram": "dg-key-123"},
    )
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


def test_deepgram_missing_key_raises():
    ctx = _ctx(stt_provider="deepgram", org_keys={})
    with pytest.raises(MissingAPIKeyError) as exc_info:
        create_stt_plugin(ctx)
    assert exc_info.value.provider == "deepgram"


def test_deepgram_key_as_dict():
    from livekit.plugins.deepgram import STT

    ctx = _ctx(
        stt_provider="deepgram",
        org_keys={"deepgram": {"api_key": "dg-nested-key"}},
    )
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


# ── Sarvam AI ─────────────────────────────────────────────────────────────────

def test_sarvam_stt_created():
    from naaviq.voice.stt.sarvam import SarvamSTT

    ctx = _ctx(
        stt_provider="sarvam",
        agent_language="hi-IN",
        org_keys={"sarvam": "sarvam-key-abc"},
    )
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, SarvamSTT)


def test_sarvam_missing_key_raises():
    ctx = _ctx(stt_provider="sarvam", org_keys={})
    with pytest.raises(MissingAPIKeyError) as exc_info:
        create_stt_plugin(ctx)
    assert exc_info.value.provider == "sarvam"


# ── OpenAI Whisper ────────────────────────────────────────────────────────────

def test_openai_stt_created():
    from livekit.plugins.openai import STT

    ctx = _ctx(stt_provider="openai", org_keys={"openai": "sk-test-key"})
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


def test_openai_stt_custom_model():
    from livekit.plugins.openai import STT

    ctx = _ctx(
        stt_provider="openai",
        stt_model="gpt-4o-transcribe",
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


def test_openai_stt_language_truncation():
    """BCP-47 'en-US' should be passed to OpenAI as 'en' (ISO 639-1)."""
    from livekit.plugins.openai import STT

    ctx = _ctx(
        stt_provider="openai",
        agent_language="en-US",
        org_keys={"openai": "sk-test-key"},
    )
    plugin = create_stt_plugin(ctx)
    assert isinstance(plugin, STT)


def test_openai_missing_key_raises():
    ctx = _ctx(stt_provider="openai", org_keys={})
    with pytest.raises(MissingAPIKeyError):
        create_stt_plugin(ctx)


# ── Unknown provider ──────────────────────────────────────────────────────────

def test_unknown_provider_raises():
    ctx = _ctx(stt_provider="whisper", org_keys={"whisper": "key"})
    with pytest.raises(ProviderNotFoundError) as exc_info:
        create_stt_plugin(ctx)
    assert exc_info.value.provider == "whisper"
    assert exc_info.value.category == "stt"
