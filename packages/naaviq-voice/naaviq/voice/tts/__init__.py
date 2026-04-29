"""
TTS provider factory for naaviq-voice.

Thin wrapper around the provider registry. All TTS logic lives in
naaviq.voice.providers.tts.*  — add new providers there.
"""

# Ensure all providers are registered before any lookup
import naaviq.voice.providers  # noqa: F401
from naaviq.voice.pipeline.context import VoiceCallContext
from naaviq.voice.providers.registry import ProviderRegistry


def create_tts_plugin(context: VoiceCallContext):
    """
    Return a LiveKit TTS plugin for the provider specified in the call context.

    Raises:
        ProviderNotFoundError: provider is not registered.
        MissingAPIKeyError: org has no API key for the provider.
    """
    provider = ProviderRegistry.get_tts(context.tts_provider)
    return provider.create_plugin(context)
