"""
TTS provider factory for vaaniq-voice.

Thin wrapper around the provider registry. All TTS logic lives in
vaaniq.voice.providers.tts.*  — add new providers there.
"""

# Ensure all providers are registered before any lookup
import vaaniq.voice.providers  # noqa: F401

from vaaniq.voice.pipeline.context import VoiceCallContext
from vaaniq.voice.providers.registry import ProviderRegistry


def create_tts_plugin(context: VoiceCallContext):
    """
    Return a LiveKit TTS plugin for the provider specified in the call context.

    Raises:
        ProviderNotFoundError: provider is not registered.
        MissingAPIKeyError: org has no API key for the provider.
    """
    provider = ProviderRegistry.get_tts(context.tts_provider)
    return provider.create_plugin(context)
