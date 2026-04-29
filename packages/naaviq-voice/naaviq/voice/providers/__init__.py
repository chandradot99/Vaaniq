"""
naaviq.voice.providers — Provider registry and all registered STT/TTS providers.

Importing this module (or any submodule) automatically registers all providers
with the ProviderRegistry via class decorators.

Public API:
    ProviderRegistry   — look up providers by ID
    STTProviderBase    — base class for STT providers
    TTSProviderBase    — base class for TTS providers
    ModelInfo          — describes a model
    VoiceInfo          — describes a voice

Usage:
    from naaviq.voice.providers import ProviderRegistry

    provider = ProviderRegistry.get_tts("elevenlabs")
    voices = await provider.fetch_voices(api_key)
"""

# Register all providers by importing them (class decorators do the registration)
from naaviq.voice.providers import stt as _stt_providers  # noqa: F401
from naaviq.voice.providers import tts as _tts_providers  # noqa: F401

from naaviq.voice.providers.base import ModelInfo, STTProviderBase, TTSProviderBase, VoiceInfo
from naaviq.voice.providers.registry import ProviderRegistry

__all__ = [
    "ProviderRegistry",
    "STTProviderBase",
    "TTSProviderBase",
    "ModelInfo",
    "VoiceInfo",
]
